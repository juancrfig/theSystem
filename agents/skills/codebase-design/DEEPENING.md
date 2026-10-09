# Deepening

How to deepen a cluster of shallow modules safely, given its dependencies. Assumes the vocabulary in [SKILL.md](SKILL.md): **module**, **interface**, **seam**, **adapter**.

## Dependency categories

When assessing a candidate for deepening, classify its dependencies. The category determines where the seam goes and whether the deepened module needs an adapter.

### 1. In-process

Pure computation, in-memory state, no I/O. Always deepenable: merge the modules and call the new interface directly. No adapter needed.

### 2. Local-substitutable

Dependencies that have local stand-ins (PGLite for Postgres, in-memory filesystem). Deepenable if the stand-in exists. The seam is internal; no port at the module's external interface.

### 3. Remote but owned (Ports & Adapters)

Your own services across a network boundary (microservices, internal APIs). Define a **port** (interface) at the seam. The deep module owns the logic; the transport is injected as an **adapter**: HTTP, gRPC or a queue in production, in-memory locally.

Recommendation shape: *"Define a port at the seam and inject the transport as an adapter, so the logic sits in one deep module even though it's deployed across a network."*

### 4. True external

Third-party services (Stripe, Twilio, etc.) you don't control. The deepened module takes the external dependency as an injected port.

## Seam discipline

- **One adapter means a hypothetical seam. Two adapters means a real one.** Don't introduce a port unless at least two adapters are justified. A single-adapter seam is just indirection.
- **Internal seams vs external seams.** A deep module can have internal seams (private to its implementation) as well as the external seam at its interface. Don't expose internal seams through the interface.

Tests follow `../../rules/tests-and-verification-need-human-approval.md`: deepening does not create or change tests unless the human approved them.
