# Third-party projects

Before a research or design document recommends a third-party project:

- Treat its README as a claim. Find the call sites and cite `file:line`. A symbol with no non-test caller does not ship.
- Test an absolute claim by trying to break it. A feature can exist and still be described too strongly.
- Read every licence file first, `NOTICE` included, and check each directory. A licence restricts copying the code, not learning a fact from it.
- Ask what the author sells. A recommended control that is the author's own product needs independent evidence.
- Check whether the argument assumes away a control this repository already runs.
- Say whether you established the mechanism or only a correlation.
