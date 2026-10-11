---
description: >-
  A small StepUp Queue workflow that submits static and generated SLURM job scripts,
  with all files of the example and the plan.py that ties them together.
---

# Basic SLURM example

The latest version of this example can be found at:
<https://github.com/reproducible-reporting/stepup-queue/tree/main/docs/examples/slurm-basic/>

This example shows how to use StepUp to run job scripts,
which can be either manually written (static) or generated from a template (dynamic).
Since these jobs only take a few seconds and don't perform any computations,
they allow for a quick demonstration of StepUp Queue's features.

## Files

```text
.
├── dynamic-template.sh
├── fail
│   └── slurmjob.sh
├── parts-template.sh
├── pass
│   └── slurmjob.py
├── plan.py
└── README.md
```

`plan.py` is a Python script that defines the workflow:

```python
{% include 'examples/slurm-basic/plan.py' %}
```

The job `fail/slurmjob.sh` is a static job script that fails with a non-zero exit code,
which is correctly handled by StepUp Queue:

```bash
{% include 'examples/slurm-basic/fail/slurmjob.sh' %}
```

The job `pass/slurmjob.py` shows how to write a Job script in Python:

```python
{% include 'examples/slurm-basic/pass/slurmjob.py' %}
```

The file `dynamic-template.sh` is a template from which actual job scripts are generated:

```bash
{% include 'examples/slurm-basic/dynamic-template.sh' %}
```

Note that `render_jinja` can be used to render any kind of text-based file from a template,
such as inputs to computational tools, configuration files, etc.

## Resubmitting a Job Only When Outputs Are Missing

The job generated from `parts-template.sh` computes a number of parts,
each of which is written to a separate output file.
Parts whose output already exists are skipped:

```bash
{% include 'examples/slurm-basic/parts-template.sh' %}
```

This job is submitted with `onchange="resubmit"` and a `complete` command,
which checks that all output files exist.
The following scenarios illustrate how the two work together:

1. Run the workflow with `NUM_PARTS = 3` in `plan.py`.
   The job computes parts 0, 1 and 2.
2. Increase `NUM_PARTS` to 5 and run the workflow again.
   The job script has changed, and the `complete` command fails
   because `part3.txt` and `part4.txt` do not exist yet.
   The job is therefore resubmitted, and the new job only computes parts 3 and 4.
3. Add a comment to `parts-template.sh` and run the workflow again.
   The job script has changed again, but the `complete` command now succeeds.
   The existing job is kept and nothing is submitted.

Without the `complete` command, the third scenario would resubmit a job that has nothing to do,
which still has to wait in the queue.
With `onchange="ignore"` instead, the second scenario would fail,
because the existing job did not produce the new outputs.

The wall time requested by the job is estimated from the number of parts,
assuming that none of them is complete yet.
When parts are skipped, the job simply ends before its wall time limit.
