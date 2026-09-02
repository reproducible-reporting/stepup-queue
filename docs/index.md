---
title: Submit SLURM jobs from a StepUp workflow
description: >-
  StepUp Queue submits SLURM jobs as steps of a StepUp workflow,
  waits for them to finish and resumes from queued jobs after a restart.
---

<!--
SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
SPDX-License-Identifier: CC-BY-SA-4.0
-->

<!-- The front matter sets the HTML title of the page, not a second heading. -->
<!-- pyml disable-num-lines 3 single-title -->

# StepUp Queue: Submit SLURM jobs from a StepUp workflow

<!-- snipwise.md BEGIN abstract -->
StepUp Queue is an experimental [StepUp](https://reproducible-reporting.github.io/stepup-core)
extension to integrate queued jobs into a workflow.
It currently supports integration with [SLURM](https://slurm.schedmd.com/)
and is designed to be extensible to other job schedulers.
<!-- snipwise.md END abstract -->

A simple example of a dataset created with StepUp Queue,
is the
[Sodium Chloride Electrolyte Equilibrium Molecular Dynamics Simulations](https://doi.org/10.5281/zenodo.15699683)
dataset on Zenodo.
