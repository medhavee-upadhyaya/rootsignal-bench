# Security policy

Please do not report vulnerabilities through public issues. Use GitHub's private vulnerability reporting for the repository. Include affected revision, reproduction steps, impact, and suggested mitigation when available.

RootSignal is a research reference implementation. Its included tools are fixture-scoped and read-only. Review the threat model before connecting it to production systems.

## Automated gates

Every push scans the complete Git history for credentials, blocks high-severity
vulnerabilities in production dependencies, and blocks critical vulnerabilities
anywhere in the dependency graph. Development-tool advisories below critical
remain visible in dependency reports and are upgraded when compatible fixes are
available; they do not represent packages shipped in the production runtime.
