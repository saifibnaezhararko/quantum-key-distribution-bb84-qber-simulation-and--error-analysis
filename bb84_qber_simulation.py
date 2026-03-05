import random
import threading
import time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

from qunetsim.components import Host, Network
from qunetsim.objects import Qubit

QBER_ABORT_THRESHOLD = 0.11
NUM_QUBITS           = 200
SIFT_FRACTION        = 0.5
CHECK_FRACTION       = 0.25

FIBER_LENGTH_KM      = 10.0
SPEED_IN_FIBER       = 2e5
EXPECTED_TRANSIT_NS  = (FIBER_LENGTH_KM / SPEED_IN_FIBER) * 1e12
QTA_TOLERANCE_NS     = 2.0
EVE_RELAY_DELAY_NS   = 15.0


def prepare_qubit(host: Host, bit: int, basis: int) -> Qubit:
    q = Qubit(host)
    if bit == 1:
        q.X()
    if basis == 1:
        q.H()
    return q


def measure_qubit(q: Qubit, basis: int) -> int:
    if basis == 1:
        q.H()
    return q.measure()


class BB84Simulation:

    def __init__(
        self,
        eve_intercept_rate: float = 0.0,
        channel_noise:      float = 0.01,
        enable_qta:         bool  = True,
        num_qubits:         int   = NUM_QUBITS,
        verbose:            bool  = False,
    ):
        self.intercept_rate = eve_intercept_rate
        self.channel_noise  = channel_noise
        self.enable_qta     = enable_qta
        self.num_qubits     = num_qubits
        self.verbose        = verbose

        self.alice_bits:   list = []
        self.alice_bases:  list = []
        self.bob_bits:     list = []
        self.bob_bases:    list = []
        self.eve_bases:    list = []
        self.eve_bits:     list = []
        self.intercepted:  list = []
        self.arrival_times: list = []

        self.sifted_alice: list = []
        self.sifted_bob:   list = []
        self.qber:         float = 0.0
        self.session_aborted: bool = False
        self.qta_alerts:   int  = 0
        self.final_key:    list = []

    def _simulate_qta(self) -> int:
        alerts = 0
        for was_intercepted in self.intercepted:
            jitter = np.random.normal(0, 0.5)
            if was_intercepted:
                delay = EVE_RELAY_DELAY_NS + np.random.normal(0, 1.0)
            else:
                delay = 0.0
            arrival = EXPECTED_TRANSIT_NS + jitter + delay
            self.arrival_times.append(arrival)
            if abs(arrival - EXPECTED_TRANSIT_NS) > QTA_TOLERANCE_NS:
                alerts += 1
        return alerts

    def run(self) -> dict:
        n = self.num_qubits

        self.alice_bits  = [random.randint(0, 1) for _ in range(n)]
        self.alice_bases = [random.randint(0, 1) for _ in range(n)]
        self.bob_bases   = [random.randint(0, 1) for _ in range(n)]
        self.eve_bases   = [random.randint(0, 1) for _ in range(n)]
        self.intercepted = [random.random() < self.intercept_rate for _ in range(n)]

        received_by_bob = []
        self.eve_bits = []

        for i in range(n):
            bit    = self.alice_bits[i]
            a_base = self.alice_bases[i]
            b_base = self.bob_bases[i]
            e_base = self.eve_bases[i]

            if self.intercepted[i]:
                if e_base == a_base:
                    e_bit = bit
                else:
                    e_bit = random.randint(0, 1)
                self.eve_bits.append(e_bit)

                if e_base != a_base:
                    if b_base == a_base:
                        bob_bit = random.randint(0, 1)
                    else:
                        bob_bit = random.randint(0, 1)
                else:
                    if b_base == a_base:
                        bob_bit = bit
                    else:
                        bob_bit = random.randint(0, 1)
            else:
                self.eve_bits.append(None)
                if b_base == a_base:
                    bob_bit = bit
                else:
                    bob_bit = random.randint(0, 1)

            if b_base == a_base and random.random() < self.channel_noise:
                bob_bit = 1 - bob_bit

            received_by_bob.append(bob_bit)

        self.bob_bits = received_by_bob

        sifted_indices = [i for i in range(n) if self.alice_bases[i] == self.bob_bases[i]]
        self.sifted_alice = [self.alice_bits[i]  for i in sifted_indices]
        self.sifted_bob   = [self.bob_bits[i]    for i in sifted_indices]

        m = max(1, int(len(sifted_indices) * CHECK_FRACTION))
        check_indices = random.sample(range(len(sifted_indices)), min(m, len(sifted_indices)))
        mismatches = sum(
            1 for idx in check_indices
            if self.sifted_alice[idx] != self.sifted_bob[idx]
        )
        self.qber = mismatches / len(check_indices) if check_indices else 0.0

        self.qta_alerts = self._simulate_qta()

        qta_abort = self.enable_qta and (self.qta_alerts > n * 0.05)
        self.session_aborted = (self.qber > QBER_ABORT_THRESHOLD) or qta_abort

        if not self.session_aborted:
            key_indices = [i for i in range(len(sifted_indices)) if i not in check_indices]
            raw_key = [self.sifted_alice[i] for i in key_indices]
            half = len(raw_key) // 2
            self.final_key = [a ^ b for a, b in zip(raw_key[:half], raw_key[half:half*2])]
        else:
            self.final_key = []

        if self.verbose:
            self._print_summary()

        return {
            "intercept_rate":    self.intercept_rate,
            "qber":              self.qber,
            "sifted_length":     len(sifted_indices),
            "final_key_length":  len(self.final_key),
            "session_aborted":   self.session_aborted,
            "qta_alerts":        self.qta_alerts,
            "qta_abort":         qta_abort,
        }

    def _print_summary(self):
        sep = "-" * 55
        print(sep)
        print(f"  Eve intercept rate : {self.intercept_rate*100:.0f}%")
        print(f"  Qubits transmitted : {self.num_qubits}")
        print(f"  Sifted key length  : {len(self.sifted_alice)}")
        print(f"  QBER               : {self.qber*100:.2f}%")
        print(f"  QTA alerts         : {self.qta_alerts} / {self.num_qubits}")
        print(f"  Session aborted    : {self.session_aborted}")
        print(f"  Final key length   : {len(self.final_key)}")
        print(sep)


def run_qunetsim_demo(num_qubits: int = 20, eve_intercept_rate: float = 0.5):
    print("\n" + "=" * 55)
    print("  QuNetSim Live Demo -- 3-Node BB84 Network")
    print(f"  Eve intercept rate: {eve_intercept_rate*100:.0f}%")
    print("=" * 55)

    network = Network.get_instance()
    network.start()

    alice = Host("Alice")
    eve   = Host("Eve")
    bob   = Host("Bob")

    alice.add_connection("Eve")
    eve.add_connection("Alice")
    eve.add_connection("Bob")
    bob.add_connection("Eve")

    network.add_host(alice)
    network.add_host(eve)
    network.add_host(bob)

    alice.start()
    eve.start()
    bob.start()

    alice_bits_shared  = []
    alice_bases_shared = []
    bob_results_shared = []
    bob_bases_shared   = []
    lock = threading.Lock()
    done_event = threading.Event()

    def alice_protocol(host: Host):
        bits  = [random.randint(0, 1) for _ in range(num_qubits)]
        bases = [random.randint(0, 1) for _ in range(num_qubits)]
        with lock:
            alice_bits_shared.extend(bits)
            alice_bases_shared.extend(bases)
        for i, (bit, basis) in enumerate(zip(bits, bases)):
            q = prepare_qubit(host, bit, basis)
            host.send_qubit("Eve", q, await_ack=False)
            time.sleep(0.05)

    def eve_protocol(host: Host):
        forwarded = 0
        while forwarded < num_qubits:
            q = host.get_data_qubit("Alice", wait=15)
            if q is None:
                break
            if random.random() < eve_intercept_rate:
                e_basis = random.randint(0, 1)
                e_bit   = measure_qubit(q, e_basis)
                q2 = prepare_qubit(host, e_bit, e_basis)
                host.send_qubit("Bob", q2, await_ack=False)
            else:
                host.send_qubit("Bob", q, await_ack=False)
            forwarded += 1

    def bob_protocol(host: Host):
        bases   = [random.randint(0, 1) for _ in range(num_qubits)]
        results = []
        with lock:
            bob_bases_shared.extend(bases)
        received = 0
        while received < num_qubits:
            q = host.get_data_qubit("Eve", wait=20)
            if q is None:
                break
            bit = measure_qubit(q, bases[received])
            results.append(bit)
            received += 1
        with lock:
            bob_results_shared.extend(results)
        done_event.set()

    t_alice = threading.Thread(target=alice_protocol, args=(alice,))
    t_eve   = threading.Thread(target=eve_protocol,   args=(eve,))
    t_bob   = threading.Thread(target=bob_protocol,   args=(bob,))

    t_alice.start(); t_eve.start(); t_bob.start()
    done_event.wait(timeout=120)
    t_alice.join(timeout=10); t_eve.join(timeout=10); t_bob.join(timeout=10)

    network.stop(stop_hosts=True)

    n_received = min(len(alice_bits_shared), len(bob_results_shared),
                     len(alice_bases_shared), len(bob_bases_shared))
    sifted_a, sifted_b = [], []
    for i in range(n_received):
        if alice_bases_shared[i] == bob_bases_shared[i]:
            sifted_a.append(alice_bits_shared[i])
            sifted_b.append(bob_results_shared[i])

    if not sifted_a:
        print("  No sifted bits -- network timeout.")
        return None

    errors = sum(a != b for a, b in zip(sifted_a, sifted_b))
    qber   = errors / len(sifted_a)
    print(f"  Qubits received     : {n_received}")
    print(f"  Sifted key length   : {len(sifted_a)}")
    print(f"  Errors              : {errors}")
    print(f"  QBER                : {qber*100:.2f}%")
    print(f"  Session aborted     : {qber > QBER_ABORT_THRESHOLD}")
    return qber


def sweep_intercept_rates(
    rates: list = None,
    trials_per_rate: int = 10,
    noise: float = 0.01,
    num_qubits: int = NUM_QUBITS,
) -> dict:
    if rates is None:
        rates = np.linspace(0.0, 1.0, 21).tolist()

    results = {"rates": [], "qber_mean": [], "qber_std": [], "abort_frac": []}

    for rate in rates:
        qbers   = []
        aborted = 0
        for _ in range(trials_per_rate):
            sim = BB84Simulation(
                eve_intercept_rate=rate,
                channel_noise=noise,
                enable_qta=True,
                num_qubits=num_qubits,
            )
            r = sim.run()
            qbers.append(r["qber"])
            if r["session_aborted"]:
                aborted += 1

        results["rates"].append(rate)
        results["qber_mean"].append(float(np.mean(qbers)))
        results["qber_std"].append(float(np.std(qbers)))
        results["abort_frac"].append(aborted / trials_per_rate)

    return results


def plot_results(sweep_data: dict, output_path: str = "bb84_qber_analysis.png"):
    rates       = np.array(sweep_data["rates"]) * 100
    qber_mean   = np.array(sweep_data["qber_mean"]) * 100
    qber_std    = np.array(sweep_data["qber_std"])  * 100
    abort_frac  = np.array(sweep_data["abort_frac"]) * 100

    fig = plt.figure(figsize=(16, 12))
    fig.patch.set_facecolor("#0d1117")
    gs = GridSpec(2, 2, figure=fig, hspace=0.40, wspace=0.35)

    ACCENT   = "#58a6ff"
    RED      = "#f85149"
    GREEN    = "#3fb950"
    YELLOW   = "#d29922"
    GRAY     = "#8b949e"
    BG       = "#161b22"
    TEXT     = "#c9d1d9"

    def style_ax(ax, title):
        ax.set_facecolor(BG)
        ax.set_title(title, color=TEXT, fontsize=12, fontweight="bold", pad=10)
        ax.tick_params(colors=GRAY)
        ax.xaxis.label.set_color(GRAY)
        ax.yaxis.label.set_color(GRAY)
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")

    ax1 = fig.add_subplot(gs[0, 0])
    style_ax(ax1, "QBER vs Eve Intercept Rate")

    ax1.fill_between(rates, qber_mean - qber_std, qber_mean + qber_std,
                     alpha=0.25, color=ACCENT)
    ax1.plot(rates, qber_mean, color=ACCENT, lw=2, marker="o",
             markersize=4, label="Measured QBER")

    theo = rates * 0.25
    ax1.plot(rates, theo, color=YELLOW, lw=1.5, linestyle="--",
             label="Theoretical (0.25*rate)")

    ax1.axhline(QBER_ABORT_THRESHOLD * 100, color=RED, lw=2, linestyle=":",
                label=f"Abort threshold ({QBER_ABORT_THRESHOLD*100:.0f}%)")
    ax1.fill_between(rates, QBER_ABORT_THRESHOLD * 100, 30,
                     alpha=0.12, color=RED, label="Abort zone")

    ax1.set_xlabel("Eve Intercept Rate (%)")
    ax1.set_ylabel("QBER (%)")
    ax1.set_xlim(0, 100); ax1.set_ylim(0, 28)
    ax1.legend(fontsize=8, facecolor=BG, edgecolor="#30363d",
               labelcolor=TEXT, loc="upper left")
    ax1.grid(alpha=0.15, color=GRAY)

    crossover_rate = QBER_ABORT_THRESHOLD / 0.25 * 100
    ax1.axvline(crossover_rate, color=RED, lw=1, linestyle="--", alpha=0.5)
    ax1.annotate(f"~{crossover_rate:.0f}%", xy=(crossover_rate, 2),
                 color=RED, fontsize=9, ha="center")

    ax2 = fig.add_subplot(gs[0, 1])
    style_ax(ax2, "Session Abort Rate vs Eve Activity")

    bar_colors = [RED if a > 50 else (YELLOW if a > 10 else GREEN) for a in abort_frac]
    ax2.bar(rates, abort_frac, width=4.5, color=bar_colors, edgecolor="#30363d", linewidth=0.5)
    ax2.axhline(50, color=YELLOW, lw=1.5, linestyle="--", alpha=0.7,
                label="50% abort rate")
    ax2.set_xlabel("Eve Intercept Rate (%)")
    ax2.set_ylabel("Sessions Aborted (%)")
    ax2.set_xlim(-3, 103); ax2.set_ylim(0, 110)
    ax2.legend(fontsize=8, facecolor=BG, edgecolor="#30363d", labelcolor=TEXT)
    ax2.grid(alpha=0.15, color=GRAY, axis="y")

    safe_patch   = mpatches.Patch(color=GREEN,  label="Safe (<10% abort)")
    warn_patch   = mpatches.Patch(color=YELLOW, label="Warning (10-50%)")
    danger_patch = mpatches.Patch(color=RED,    label="Dangerous (>50%)")
    ax2.legend(handles=[safe_patch, warn_patch, danger_patch],
               fontsize=8, facecolor=BG, edgecolor="#30363d", labelcolor=TEXT)

    ax3 = fig.add_subplot(gs[1, 0])
    style_ax(ax3, "Quantum Temporal Authentication (QTA) -- Arrival Times")

    np.random.seed(42)
    normal_arrivals     = np.random.normal(EXPECTED_TRANSIT_NS, 0.5, 200)
    intercepted_arr     = np.random.normal(EXPECTED_TRANSIT_NS + EVE_RELAY_DELAY_NS, 1.5, 100)

    ax3.hist(normal_arrivals, bins=40, color=GREEN, alpha=0.7,
             label="Legitimate photons", density=True)
    ax3.hist(intercepted_arr, bins=40, color=RED, alpha=0.7,
             label="Eve-relayed photons", density=True)
    ax3.axvline(EXPECTED_TRANSIT_NS, color=ACCENT, lw=2, label="Expected arrival")
    ax3.axvspan(EXPECTED_TRANSIT_NS - QTA_TOLERANCE_NS,
                EXPECTED_TRANSIT_NS + QTA_TOLERANCE_NS,
                alpha=0.15, color=ACCENT, label=f"+-{QTA_TOLERANCE_NS} ns window")

    ax3.set_xlabel("Photon Arrival Time (ns)")
    ax3.set_ylabel("Probability Density")
    ax3.legend(fontsize=8, facecolor=BG, edgecolor="#30363d", labelcolor=TEXT)
    ax3.grid(alpha=0.15, color=GRAY)
    center_ns = EXPECTED_TRANSIT_NS
    ax3.set_xlim(center_ns - 5, center_ns + EVE_RELAY_DELAY_NS + 10)

    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor(BG)
    ax4.axis("off")
    style_ax(ax4, "BB84 + QTA Security Summary")

    table_data = [
        ["Eve Intercept", "Theoretical", "Abort"],
        ["Rate (%)",      "QBER (%)",    "Decision"],
        ["---------",     "---------",   "---------"],
        ["0%",            "0.0%",        "OK Secure"],
        ["10%",           "2.5%",        "OK Secure"],
        ["20%",           "5.0%",        "OK Secure (check)"],
        ["44%",           "11.0%",       "! Abort threshold"],
        ["50%",           "12.5%",       "X Abort (QBER)"],
        ["75%",           "18.75%",      "X Abort (QBER)"],
        ["100%",          "25.0%",       "X Abort (QBER+QTA)"],
        ["---------",     "---------",   "---------"],
        ["Any",           "Any",         "X QTA: relay >2 ns"],
    ]

    row_colors = [
        [ACCENT]*3, [GRAY]*3, [GRAY]*3,
        [GREEN]*3, [GREEN]*3, [GREEN]*3, [YELLOW]*3,
        [RED]*3, [RED]*3, [RED]*3,
        [GRAY]*3, [RED]*3,
    ]

    y_start = 0.95
    col_x   = [0.05, 0.42, 0.72]
    for r, (row, rcolors) in enumerate(zip(table_data, row_colors)):
        y = y_start - r * 0.075
        for c, (cell, color) in enumerate(zip(row, rcolors)):
            weight = "bold" if r < 2 else "normal"
            ax4.text(col_x[c], y, cell, transform=ax4.transAxes,
                     color=color, fontsize=9, fontweight=weight,
                     verticalalignment="top", fontfamily="monospace")

    fig.suptitle(
        "Module 3: BB84 Quantum Key Distribution -- QBER & Security Analysis\n"
        "Alice  --->  Eve (Intercept-Resend)  --->  Bob  |  QTA: +-2 ns Timing Window",
        color=TEXT, fontsize=13, fontweight="bold", y=0.98
    )

    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"\n  [+] Figure saved -> {output_path}")
    return output_path


def main():
    print("=" * 58)
    print("  Module 3: Securing Quantum Channel")
    print("  BB84 + QTA -- QBER Threshold Simulation")
    print("=" * 58)

    print("\n[1] Single-run examples at key intercept rates:\n")
    test_rates = [0.0, 0.25, 0.44, 0.50, 0.75, 1.0]
    for rate in test_rates:
        sim = BB84Simulation(
            eve_intercept_rate=rate,
            channel_noise=0.01,
            enable_qta=True,
            num_qubits=500,
            verbose=True,
        )
        sim.run()

    print("\n[2] Statistical sweep (20 intercept rates x 15 trials)...")
    sweep_data = sweep_intercept_rates(
        rates=np.linspace(0.0, 1.0, 21).tolist(),
        trials_per_rate=15,
        noise=0.01,
        num_qubits=300,
    )

    print("\n  Rate(%)  |  QBER mean +- std  |  Abort %")
    print("  " + "-" * 44)
    for i, rate in enumerate(sweep_data["rates"]):
        abort = sweep_data["abort_frac"][i] * 100
        qber  = sweep_data["qber_mean"][i] * 100
        std   = sweep_data["qber_std"][i]  * 100
        flag  = " <- ABORT" if qber > QBER_ABORT_THRESHOLD * 100 else ""
        print(f"  {rate*100:>6.0f}%  |  {qber:5.2f}% +- {std:.2f}%     |  {abort:5.1f}%{flag}")

    print("\n[3] Generating analysis figure...")
    plot_path = "d:/quantum cairo projects/qkd/module 3 task/bb84_qber_analysis.png"
    plot_results(sweep_data, output_path=plot_path)

    print("\n[4] QuNetSim live 3-node network demo (Eve at 50%)...")
    try:
        qber_live = run_qunetsim_demo(num_qubits=30, eve_intercept_rate=0.50)
        if qber_live is not None:
            verdict = "ABORT -- session compromised" if qber_live > QBER_ABORT_THRESHOLD \
                      else "SECURE -- key accepted"
            print(f"\n  Live QBER: {qber_live*100:.2f}%  ->  {verdict}")
    except Exception as exc:
        print(f"  QuNetSim live demo skipped: {exc}")

    print("\n" + "=" * 58)
    print("  Simulation complete.")
    print(f"  QBER abort threshold : {QBER_ABORT_THRESHOLD*100:.0f}% (Shor-Preskill)")
    print("  QTA timing window    : +-2 ns")
    print("=" * 58)


if __name__ == "__main__":
    main()
