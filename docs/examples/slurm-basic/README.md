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
