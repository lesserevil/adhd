# Framework flow

[Project guide](../README.md) → framework flow

Specifications define behavior; selected Flavors add target requirements; exact skills
guide conversion; workflows and routing constrain model work. Generated source is
disposable and lives beneath the project's generated cache or an isolated runtime.
The project's `+make` selection is a removable target preference: explicit
specification requirements and selected Flavors take precedence, and `-make`
removes it before prompt assembly.

```mermaid
flowchart TD
    Read[Read specifications] --> Plan[litai plan]
    Plan --> Generate[litai generate]
    Generate --> Validate[Validate and classify]
    Validate --> Authorize{Authorized?}
    Authorize -- yes --> Build[Build]
    Build --> Test[Test known behavior]
    Authorize -- no --> Stop[Stop safely]
```

Use the [project map](project-layout.md) to change the owning artifact, and read
[security](security.md) before compiling or running generated code.
