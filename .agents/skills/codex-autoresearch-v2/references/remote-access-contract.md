# Remote access contract

The local remote-access layer owns:

- example/local configuration loading and session-scoped Profile resolution;
- OpenSSH/SCP calls through one immutable access context;
- optional tunnel startup and remote HTTP-proxy diagnostics.

The controller consumes that context without parsing Profile fields or building
SSH/SCP arguments. The server bridge receives runtime arguments only; it knows
nothing about local Profiles, SSH configuration, or proxies.

Keep credentials, host-key policy, and jump routing in OpenSSH config; machine
Profiles and server roots in `config/autoresearch-v2.local.psd1`; repository
paths and commands in the target. A Profile may override the `Remote*` runtime
roots when accounts or servers use different home directories. The controller
must resolve those overrides from the same selected Profile used for SSH.

A Codex session resolves its Profile once on first enable and locks it until
the user explicitly switches. `ActiveRemoteProfile` is only the default for
that first resolution; it is not a per-call fallback. Profile keys are
machine-scoped (for example `lab929-4090`), never account names.

When direct server synchronization is enabled, the controller uses the
selected server repository as the local git remote. The URL comes from the
Profile's `LocalGitRemoteUrl` when set; otherwise it is derived from the same
access context (`RemoteHost` plus the target repository's `repo.path`). Git
uses the same SSH config and batch-mode settings as SSH/SCP, so
synchronization adds no extra credential or confirmation step. `sync` may fetch
an exact branch with `-Checkout -CheckoutBranch <branch>`.

Profiles may declare `ExpectedHostname` and `ExpectedUser`. `access-doctor`
compares them with `hostname; whoami` on the connected host and fails on
mismatch; the check is automatic and adds no confirmation step.

`ProxyMode` is `disabled`, `optional`, or `required`. Optional proxy failures do
not fail `access-doctor`; required proxy failures do. `access-ensure` may start
only the configured `LocalTunnelScript`.
