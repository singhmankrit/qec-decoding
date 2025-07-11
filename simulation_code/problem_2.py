import stim
import pymatching
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm


# Problem 2A
def generate_repetition_code_circuit(d, p, q):
    """
    Generate a Stim circuit for a distance-d repetition code with separate
    phenomenological bit-flip noise on data and ancilla qubits.

    Args:
        d (int): Code distance (generally odd).
        p (float): Probability of a bit-flip (X error) on each data qubit.
        q (float): Probability of a bit-flip (X error) on each ancilla qubit.

    Returns:
        stim.Circuit: The corresponding Stim circuit with initialization,
                      error application, Hadamard gates, controlled-Z gates,
                      measurements, and resets for the repetition code process.
    """

    circuit = stim.Circuit()
    total_qubits = 2 * d - 1

    # First initalise d data qubits and d-1 ancilla qubits
    for qubit in range(total_qubits):
        circuit.append("R", [qubit])

    for _ in range(d - 1):
        for i in range(total_qubits):
            if i % 2 == 0:
                circuit.append_operation("X_ERROR", [i], p)
            else:
                circuit.append_operation("X_ERROR", [i], q)

        for i in range(1, total_qubits, 2):
            circuit.append_operation("CNOT", [i - 1, i])
            circuit.append_operation("CNOT", [i + 1, i])
            circuit.append_operation("M", [i])
            circuit.append_operation("R", [i])

    # Measure in Z basis
    for i in range(0, total_qubits, 2):
        circuit.append_operation("X_ERROR", [i], p)
        circuit.append_operation("M", [i])

    return circuit


# Problem 2B
def measurement_sampler(circuit, n_runs, seed=42):
    """
    Samples measurement outcomes after compiling a measurement sampler.

    Args:
        circuit (stim.Circuit): The quantum circuit to be measured.
        n_runs (int): The number of times to sample the circuit.
        seed (int, optional): Random seed for reproducibility. Defaults to 42.

    Returns:
        np.ndarray: An array of measurement results, with each row corresponding
                    to a run and each column to a measured qubit.
    """

    sampler = stim.CompiledMeasurementSampler(circuit, seed=seed)
    return np.array(sampler.sample(n_runs)).astype(int)


# Problem 2C
def process_measurements(sampled_runs, d):
    """
    Process the measurement outcomes to detect defects (syndrome flip in time)

    Args:
        sampled_runs (np.ndarray): The sampled measurement outcomes
        d (int): The number of rounds

    Returns:
        list: A list of defects, where each element is a list of defects in one
              run and each element is a list of defects in each round
    """

    defects = []
    for run in sampled_runs:
        n_rounds = d
        n_ancillas = d - 1

        # Syndromes
        measured_syndromes = np.array(run[: n_ancillas * n_ancillas]).reshape(
            n_ancillas, n_ancillas
        )
        final_data = np.array(run[-d:])
        projected_syndrome = np.array(
            [final_data[i] ^ final_data[i + 1] for i in range(d - 1)]
        )
        syndrome_in_this_run = np.vstack([measured_syndromes, projected_syndrome])

        # Compute defects = syndrome flip in time
        defects_in_this_run = []
        for t in range(n_rounds):
            for i in range(n_ancillas):
                if t == 0:
                    defects_in_this_run.append(syndrome_in_this_run[0][i])
                else:
                    defect = syndrome_in_this_run[t][i] ^ syndrome_in_this_run[t - 1][i]
                    defects_in_this_run.append(defect)
        defects.append(defects_in_this_run)
    return np.array(defects, dtype=int)


# Problem 2D
def build_decoding_graph(d, p, q):
    """
    Builds a decoding graph for a distance-d surface code with separate
    phenomenological bit-flip noise on data and ancilla qubits.

    Args:
        d (int): The code distance.
        p (float): The probability of a bit-flip (X error) on each data qubit.
        q (float): The probability of a bit-flip (X error) on each ancilla qubit.

    Returns:
        pymatching.Matching: The decoding graph.
    """

    graph = pymatching.Matching()

    def get_index(d, t, i):
        return (d - 1) * t + i

    # adding space-like edges
    for t in range(d):  # loop over time
        for i in range(1, d - 1):  # loop over space
            a = get_index(d, t, i - 1)
            b = get_index(d, t, i)
            graph.add_edge(a, b, error_probability=p, fault_ids={i})

    # adding time-like edges
    for t in range(1, d):  # loop over time
        for i in range(d - 1):  # loop over space
            a = get_index(d, t - 1, i)
            b = get_index(d, t, i)
            graph.add_edge(a, b, error_probability=q, fault_ids=set())

    # Boundary edges:
    for t in range(d):
        for i in range(d - 1):
            idx = get_index(d, t, i)
            is_edge = i in [0, d - 2]

            if i == 0:
                fault_id = 0
            else:
                fault_id = d - 1

            if is_edge:
                graph.add_boundary_edge(idx, error_probability=p, fault_ids={fault_id})

    return graph


# Problem 2E
def simulate_threshold(n_runs=10**6):
    """
    Simulates the logical error rate of the repetition code using the minimum
    weight perfect matching (MWPM) algorithm for various physical error rates
    and code distances, and plots the results.

    Args:
        n_runs (int): The number of runs to perform at each physical error rate.

    Returns:
        threshold: The estimated threshold error rate.
    """

    distances = [3, 5, 7, 9]
    probabilities = np.linspace(0.05, 0.15, 20)
    results = {}

    for d in distances:
        pL_list = []
        print(f"\nSimulating for d = {d}")
        for p in tqdm(probabilities):
            circuit = generate_repetition_code_circuit(d, p, p)
            samples = measurement_sampler(circuit, n_runs=n_runs)
            defects = process_measurements(samples, d)
            graph = build_decoding_graph(d, p, p)
            corrections = graph.decode_batch(defects)
            final_data = samples[:, -d:]
            logical_outcomes = np.sum((final_data ^ corrections), axis=1) % 2
            pL = sum(logical_outcomes) / n_runs
            pL_list.append(pL)
        results[d] = pL_list

    # Estimate threshold
    threshold_p = None
    for i in range(len(probabilities) - 1):
        pL_prev_dist = -1
        all_d = True
        for d in distances:
            if i > 0 and pL_prev_dist > 0:
                # Only when the pL of distances is in increasing order do we mark the threshold
                if pL_prev_dist < results[d][i]:
                    if d == distances[-1] and all_d:
                        threshold_p = (probabilities[i - 1] + probabilities[i]) / 2
                        break
                else:
                    all_d = False
            pL_prev_dist = results[d][i]
        if threshold_p is not None:
            break

    # Plotting
    plt.figure(figsize=(10, 6))
    for d in distances:
        plt.plot(probabilities, results[d], label=f"d = {d}")

    # Plot threshold marker
    plt.axvline(
        x=threshold_p,
        color="red",
        linestyle="--",
        label=f"Estimated threshold ≈ {threshold_p:.3f}",
    )
    plt.xlabel("Physical error rate p")
    plt.ylabel("Logical error rate pL")
    plt.title("Minimum Weight Perfect Matching with Ancillas")
    plt.legend()
    plt.grid(True)
    plt.yscale("log")
    plt.savefig("images/problem_2/threshold_w_ancillas.png")

    return threshold_p
