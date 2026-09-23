# Laya A2A POC — Milestone 4

LLM-free, vLLM-free incident coordination simulator. Includes typed incident/decision/message contracts, pluggable router, deterministic rules, simulated specialist and verification agents, and bounded escalation. Milestone 2 adds the Laya SDK adapter. No model benchmark results yet.

Run with Python 3.10+ from this directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m laya_a2a.demo
```

On Windows PowerShell, activate the environment using `.venv\\Scripts\\Activate.ps1`.

To run the real Laya checkpoint in a separate Python environment with network access and adequate RAM/VRAM:

```bash
python -m pip install -e '.[laya]'
python -m laya_a2a.demo --router laya --checkpoint english
python -m laya_a2a.demo --router laya --checkpoint typed-decisions
```

The checkpoint download occurs on first load. The `english` base checkpoint and `typed-decisions` checkpoint should be evaluated separately: upstream reports weak zero-shot performance for its base checkpoint on an unrelated typed-decision benchmark. This is not evidence of incident-routing performance. Model weights are not included in this project.

The checkpoint comes from `convaiinnovations/laya` on Hugging Face; the SDK is installed from PyPI. Both hosts must be reachable. The root English checkpoint is roughly 808 MB; CPU inference works but is slower than GPU. To keep the download cache inside this project, set `HF_HOME="$PWD/.hf-cache"` before running Laya and add `.hf-cache/` to your local ignore rules. Never commit model weights. If network access is unavailable, download the checkpoint in a network-enabled environment and transfer its cache or checkpoint directory; then update `laya.load(...)` to use the local path. Verify the exact SDK and checkpoint revision before publishing performance results.

The adapter calls the documented `agent.predict(state, questions)` API in one pass for routing (`choice`), severity (`score`), and escalation (`noul`); it validates the returned values and rejects unknown agents. Its 0.5 escalation threshold is provisional. Contract tests use an injected response stub and do **not** constitute model inference.

## Curated evaluation scenarios

`data/scenarios.jsonl` contains 24 manually authored synthetic incident cases: eight each for development, calibration and test, with routing, severity, escalation and a human-readable labeling rationale. `laya_a2a.dataset.load_scenarios()` validates labels and rejects extra state fields, so labels cannot silently enter model input. `missing_fields` distinguishes unavailable telemetry from an observed zero; the Laya adapter sends null for unavailable values and the baseline skips those signals. The cases are small and **do not establish statistical performance**. Variants of the same scenario family occur in multiple splits, so these splits are useful for integration only; they do not qualify as an independent final holdout. A larger expert-reviewed set with disjoint incident families is required before a go/no-go decision. Labels reflect the author's triage policy, not verified production root causes.

## Benchmark harness

Run the same split through each router. Output consists of per-case CSV and a summary JSON:

```bash
python -m laya_a2a.benchmark --router rules --split test --warmup 5
python -m laya_a2a.benchmark --router laya --checkpoint english --split test --warmup 5
python -m laya_a2a.benchmark --router laya --checkpoint typed-decisions --split test --warmup 5
```

For Laya, install the SDK and model weights first. The harness fails explicitly if the SDK is unavailable; it never replaces model results with stub values. It records errors as misses, plus routing accuracy, macro F1, escalation recall, severity MAE, simulated workflow completion, wrong-agent calls, p50/p95/p99 decision latency and sequential throughput. Timing excludes model loading, and eight test cases are far too few for stable latency estimates. Calibration and Brier score are withheld because the current `confidence` field has not been established as a calibrated probability of routing correctness. The workflow metric here is **derived from labeled decisions**; it is not an observed production remediation success rate. The baseline JSON checked into `results/` documents only the rule run on synthetic starter cases.

`actual_owner` is simulator ground truth. The coordinator strips it before invoking the router. Agents have no real-world side effects. Rules prioritize security, database latency >500 ms, network latency >300 ms, then application error rate >0.1 or CPU >90%. These rules are a baseline, not an oracle.

## Roadmap

1. Run the real Laya checkpoint with the adapter and capture the installed package version, model revision and hardware. Confirm response fields against a live inference result.
2. Expand the starter scenarios into independently reviewed incidents, with separate families and source incidents across splits. Freeze the holdout before tuning prompts or thresholds.
3. Compare both routers on identical scenarios: routing accuracy, macro F1, escalation recall, workflow completion, wrong-agent calls, latency percentiles, throughput and resources. Assess ECE/Brier only if output scores are probabilities with appropriate semantics.
4. Calibrate abstention thresholds on a separate split. Report coverage versus errors, hardware, warmup, batch size and confidence intervals. Determine whether improvements justify added inference cost.
