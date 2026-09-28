"""
New Axial Age — Minimal Four-Wheel Prototype (v0.2)
-------------------------------------------------
Design goals (for EV sandbox first version):
1. Explicit mapping to the four wheels
2. Transparent parameters with one-line rationale
3. Simple demonstration-effect (not pure mean-field)
4. Two ready-made scenarios for comparison
5. Easy to wrap with Streamlit later

This is a heuristic toy, not a calibrated forecast model.
"""

import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass, field
from typing import List, Dict


# -------------------------------------------------
# 1. Parameters (four-wheel mapping + short rationale)
# -------------------------------------------------
@dataclass
class Params:
    # --- Wheel 1: Thermodynamic / Energy ---
    initial_Js: float = 16.0          # initial extractable free-energy stock
    depletion_rate: float = 0.004     # base stock decline per step (direct deadline pressure)
    min_complexity_cost: float = 0.25 # fixed cost to keep current social complexity

    # --- Wheel 2: Dopamine / behavioral ---
    E_crit: float = 3.0               # energy level where survival prior starts dominating
    k_gamma: float = 1.1              # steepness of energy → cooperation propensity
    baseline_reset: float = 0.015     # mild upward drift in aspiration when energy is high

    # --- Wheel 3: Supervision / rent-seeking ---
    base_supervision_friction: float = 0.08  # Re: share lost to monitoring & leakage
    supervision_chain_effect: float = 0.25   # how fast friction rises with elite extraction
    demo_sensitivity: float = 0.35    # how strongly neighbors' extraction spreads

    # --- Wheel 4: Jevons / technology ---
    efficiency_gain: float = 0.0      # exogenous efficiency improvement per step
    reinvestment_ratio: float = 0.7   # fraction of efficiency gain reinvested into higher throughput

    # --- Population & simulation ---
    n_civilians: int = 400
    n_elites: int = 50
    steps: int = 30
    elite_share: float = 0.48         # institutional capture of effective energy
    seed: int = 42


# -------------------------------------------------
# 2. Agent
# -------------------------------------------------
@dataclass
class Agent:
    id: int
    role: str                  # "civilian" | "elite"
    energy: float
    pm: float                  # resilience / prior strength (higher → slower collapse)
    gamma: float = 1.0         # cooperation propensity (0–1)
    strategy: str = "cooperate"  # "cooperate" | "extract"
    # local neighborhood indices (simple ring for demo effect)
    neighbors: List[int] = field(default_factory=list)

    def update_gamma(self, p: Params, neighbor_extract_rate: float):
        """
        Energy pressure + demonstration effect → cooperation propensity.
        """
        # logistic response to own energy
        base = 1.0 / (1.0 + np.exp(-p.k_gamma * (self.energy - p.E_crit)))
        # resilience bonus
        resilience = 0.04 * (self.pm - 6.0)
        # demonstration penalty: more extracting neighbors → lower gamma
        demo_penalty = p.demo_sensitivity * neighbor_extract_rate

        self.gamma = np.clip(base + resilience - demo_penalty, 0.0, 1.0)

        # role-specific threshold (elites switch a bit later)
        thresh = 0.40 if self.role == "elite" else 0.33
        self.strategy = "extract" if self.gamma < thresh else "cooperate"


# -------------------------------------------------
# 3. Model
# -------------------------------------------------
class FourWheelModel:
    def __init__(self, p: Params):
        self.p = p
        rng = np.random.default_rng(p.seed)

        self.agents: List[Agent] = []
        # civilians
        for i in range(p.n_civilians):
            self.agents.append(Agent(
                id=i,
                role="civilian",
                energy=rng.normal(8.2, 0.9),
                pm=rng.normal(6.0, 0.7),
            ))
        # elites
        for i in range(p.n_elites):
            self.agents.append(Agent(
                id=p.n_civilians + i,
                role="elite",
                energy=rng.normal(13.5, 1.1),
                pm=rng.normal(5.5, 0.6),
            ))

        # simple ring neighborhood (keeps demo-effect local, still very light)
        n = len(self.agents)
        for i, a in enumerate(self.agents):
            a.neighbors = [(i - 1) % n, (i + 1) % n, (i + 2) % n]

        self.Js = p.initial_Js
        self.history: List[Dict] = []

    def _neighbor_extract_rate(self, agent: Agent) -> float:
        if not agent.neighbors:
            return 0.0
        extracting = sum(
            1 for j in agent.neighbors
            if self.agents[j].strategy == "extract"
        )
        return extracting / len(agent.neighbors)

    def step(self, t: int):
        p = self.p

        # ----- Wheel 1: thermodynamic depletion -----
        self.Js = max(1.5, self.Js * (1.0 - p.depletion_rate))

        # ----- Wheel 4: Jevons (efficiency → higher throughput) -----
        # efficiency gain is partly reinvested, so effective draw on stock rises
        jevons_draw = 1.0 + p.efficiency_gain * p.reinvestment_ratio * t * 0.01
        current_Js = self.Js / jevons_draw

        elites = [a for a in self.agents if a.role == "elite"]
        civilians = [a for a in self.agents if a.role == "civilian"]
        elite_extract_ratio = (
            sum(1 for e in elites if e.strategy == "extract") / max(1, len(elites))
        )

        # ----- Wheel 3: supervision friction rises with extraction -----
        Re = min(
            0.65,
            p.base_supervision_friction
            + p.supervision_chain_effect * elite_extract_ratio
            + 0.006 * t,
        )

        J_eff = max(0.5, current_Js * (1.0 - Re) - p.min_complexity_cost)

        # distribution
        energy_elites = J_eff * p.elite_share
        energy_civ = J_eff * (1.0 - p.elite_share)

        if elites:
            base_e = energy_elites / len(elites)
            for e in elites:
                e.energy = e.energy * 0.78 + base_e * 0.22
        if civilians:
            base_c = energy_civ / len(civilians)
            for c in civilians:
                c.energy = c.energy * 0.75 + base_c * 0.25

        # extraction / mutual predation (simple transfer with friction)
        extractors = [a for a in self.agents if a.strategy == "extract"]
        if extractors and civilians:
            total_stolen = 0.0
            for ext in extractors:
                rate = 0.045 if ext.role == "elite" else 0.022
                steal = min(0.25, ext.energy * rate)
                total_stolen += steal
                ext.energy += steal * 0.80          # friction loss
            per_civ = total_stolen / len(civilians)
            for c in civilians:
                c.energy = max(0.3, c.energy - per_civ)

        # ----- Wheel 2 + demo effect: update gamma & strategy -----
        for a in self.agents:
            neigh_rate = self._neighbor_extract_rate(a)
            a.update_gamma(p, neigh_rate)
            # mild aspiration drift when energy high (baseline reset sketch)
            if a.energy > p.E_crit + 2.0:
                a.pm = np.clip(a.pm + p.baseline_reset, 0.5, 14.0)
            else:
                a.pm = np.clip(a.pm - 0.01, 0.5, 14.0)

        # record
        mean_energy = float(np.mean([a.energy for a in self.agents]))
        mean_gamma = float(np.mean([a.gamma for a in self.agents]))
        n_extract = sum(1 for a in self.agents if a.strategy == "extract")
        elite_coop = sum(1 for e in elites if e.strategy == "cooperate")
        civ_coop = sum(1 for c in civilians if c.strategy == "cooperate")

        self.history.append({
            "t": t,
            "Js": self.Js,
            "J_eff": J_eff,
            "Re": Re,
            "mean_energy": mean_energy,
            "mean_gamma": mean_gamma,
            "extractors": n_extract,
            "elite_coop": elite_coop,
            "civ_coop": civ_coop,
            "elite_extract_ratio": elite_extract_ratio,
        })

    def run(self):
        for t in range(1, self.p.steps + 1):
            self.step(t)
        return self.history


# -------------------------------------------------
# 4. Scenarios
# -------------------------------------------------
def scenario_low_friction() -> Params:
    """Lower supervision friction → slower rise of rent-seeking."""
    p = Params()
    p.base_supervision_friction = 0.05
    p.supervision_chain_effect = 0.12
    p.seed = 1
    return p


def scenario_high_friction() -> Params:
    """Higher supervision friction + stronger chain effect → faster extraction cascade."""
    p = Params()
    p.base_supervision_friction = 0.12
    p.supervision_chain_effect = 0.35
    p.demo_sensitivity = 0.45
    p.seed = 1
    return p


def scenario_with_jevons() -> Params:
    """Mild efficiency gains that are mostly reinvested (Jevons)."""
    p = Params()
    p.efficiency_gain = 0.8
    p.reinvestment_ratio = 0.85
    p.seed = 1
    return p


# -------------------------------------------------
# 5. Run & plot comparison
# -------------------------------------------------
def run_and_collect(p: Params):
    model = FourWheelModel(p)
    hist = model.run()
    return hist


if __name__ == "__main__":
    scenarios = {
        "Low supervision friction": scenario_low_friction(),
        "High supervision friction": scenario_high_friction(),
        "With Jevons reinvestment": scenario_with_jevons(),
    }

    results = {}
    for name, p in scenarios.items():
        results[name] = run_and_collect(p)

    # print last-step summary
    print(f"{'Scenario':<28} | {'J_eff':>7} | {'Re':>6} | {'Meanγ':>7} | {'Extractors':>10}")
    print("-" * 70)
    for name, hist in results.items():
        last = hist[-1]
        print(
            f"{name:<28} | {last['J_eff']:7.3f} | {last['Re']:6.3f} | "
            f"{last['mean_gamma']:7.3f} | {last['extractors']:10d}"
        )

    # plot mean_gamma trajectories
    plt.figure(figsize=(10, 5))
    for name, hist in results.items():
        ts = [h["t"] for h in hist]
        gs = [h["mean_gamma"] for h in hist]
        plt.plot(ts, gs, label=name, linewidth=2)
    plt.xlabel("Time step")
    plt.ylabel("Mean cooperation propensity (γ)")
    plt.title("New Axial Age prototype — scenario comparison")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()
