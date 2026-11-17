# Architecture

CLI -> explicit check coordinator -> fixed observation/readback children.
The lower layer supplies strict JSON, exact schemas, bounded POSIX I/O,
cooperative policy locks, exclusive publication and capped transport.

Importing `agent_evidence` only defines a lazy entrypoint; loading Python module
code is the interpreter's normal import I/O. Calling `run_checks` takes explicit
roots and manifest. No plugins, environment discovery, host registries or owner
imports exist. Runtime dependencies are standard-library-only.

The inventory coordinator admits reviewed controls before any check or inventory
source worker, then performs real presence observation/readback for source pins.
A final double policy/control observation produces one deeply immutable freeze;
six inventory coverage views share its current-clock consumption decision.
Supplied procedure evaluation consumes declarations, explicit grants and bound
assertions without executing them. The Hermes adapter generates fixed requests
from versioned explicit bindings; pure semantic evaluation runs in both children.
The final report projects those admitted results into all 21 required catalog
rows, without target reads or forbidden native checks. Neither supplied evidence
nor fresh timestamps bind a producer or restore live execution authority.
The development contracts do not claim a complete stable package.
