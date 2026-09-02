# Perpetual SLURM Workflow Job

The latest version of this example can be found at:
<https://github.com/reproducible-reporting/stepup-queue/tree/main/docs/examples/slurm-perpetual/>

For extensive workflows, it is often useful to submit the workflow itself to the queue as a job.
It is generally preferred to run the workflow on a compute node of the cluster,
as this allows for better resource management and prevents overloading the login node.
However, most clusters impose a limit on the maximum wall time of a job,
which can result in the workflow job being interrupted.
This example shows how to work around this limitation by using a perpetual self-submitting job.

At the start of the job, a background process is launched that will end StepUp
before the wall time limit is reached if StepUp has not ended on its own.
When StepUp is stopped this way, it still has work left to do,
which it reports by setting the `DRAINED` bit in its exit code.
That bit is the signal that the workflow job needs to be resubmitted.
The SLURM jobs that StepUp was waiting for are not cancelled:
they stay in the queue,
and the resubmitted workflow job picks them up again instead of submitting them a second time.
The wall time monitor itself can be used with any type of job and is not specific to StepUp.

Here, we use a very short runtime to quickly demonstrate StepUp Queue's features.
In practice, you can let the StepUp job run for several hours or even days at a time,
and stop it about 30 minutes before the wall time limit is reached.

## Files

```text
.
├── plan.py
├── README.md
├── step1
│   └── slurmjob.sh
├── step2
│   └── slurmjob.sh
└── workflow.sh
```

`plan.py` is a Python script that defines the workflow:

```python
{% include 'examples/slurm-perpetual/plan.py' %}
```

`step1/slurmjob.sh` is the first SLURM job:

```bash
{% include 'examples/slurm-perpetual/step1/slurmjob.sh' %}
```

`step2/slurmjob.sh` is the second SLURM job:

```bash
{% include 'examples/slurm-perpetual/step2/slurmjob.sh' %}
```

`workflow.sh` is the SLURM job script that runs the workflow:

```bash
{% include 'examples/slurm-perpetual/workflow.sh' %}
```
