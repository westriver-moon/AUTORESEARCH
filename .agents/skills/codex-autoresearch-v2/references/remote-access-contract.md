# Remote access contract

The local remote-access layer owns:

- example/local configuration loading and Profile resolution;
- OpenSSH/SCP calls through one immutable access context;
- optional tunnel startup and remote HTTP-proxy diagnostics.

The controller consumes that context without parsing Profile fields or building
SSH/SCP arguments. The server bridge receives runtime arguments only; it knows
nothing about local Profiles, SSH configuration, or proxies.

Keep credentials, host-key policy, and jump routing in OpenSSH config; machine
Profiles and server roots in `config/autoresearch-v2.local.psd1`; repository
paths and commands in the target.

`ProxyMode` is `disabled`, `optional`, or `required`. Optional proxy failures do
not fail `access-doctor`; required proxy failures do. `access-ensure` may start
only the configured `LocalTunnelScript`.
