@{
    # Remote access layer. Keep credentials and concrete hosts in the ignored
    # autoresearch-v2.local.psd1 file or in the user's OpenSSH configuration.
    # ActiveRemoteProfile is only the first-selection default for a new Codex
    # session; after selection the session lock wins until an explicit switch.
    ActiveRemoteProfile = ''
    RemoteHost = ''
    TunnelAlias = ''
    SshConfigPath = ''
    LocalTunnelScript = ''
    ProxyTaskName = ''
    ConnectTimeoutSec = 15
    ProxyMode = 'optional'
    LocalProxyPort = 7897
    ProxyPort = 7897
    ProxyProbeUrl = 'https://github.com'
    # Profiles may override both access settings and the Remote* runtime roots
    # below when accounts or servers use different home directories.
    # Use machine-scoped keys such as 'account-machine' rather than account
    # names. Optional ExpectedHostname/ExpectedUser fields let access-doctor
    # verify the connected host.
    RemoteProfiles = @{
        # 'example-profile' = @{
        #     DisplayName = 'Example server'
        #     HostAddress = '192.0.2.10'
        #     Port = 22
        #     User = 'research'
        #     SelectionOrder = 1
        #     RemoteHost = 'example-ssh-alias'
        #     RemoteControllerRoot = '/home/research/autoresearch-v2'
        #     RemoteRunRoot = '/home/research/autoresearch-v2/runs'
        #     RemoteWorktreeRoot = '/home/research/autoresearch-v2/worktrees'
        #     RemoteLeaseRoot = '/home/research/autoresearch-v2/leases'
        #     RemoteBridgeEntry = '/home/research/autoresearch-v2/run_autoresearch_v2_bridge.sh'
        # }
    }

    # Project-owned experiment inputs and local collection root.
    ProgramPath = 'autoresearch/program-example.md'
    TargetPath = 'autoresearch/targets/example-cpu.yaml'
    LocalRunRoot = 'autoresearch-runs'
    # Optional direct server git remote. When LocalRepositoryPath is set, the
    # controller uses the selected server repository as a git remote and
    # fetches run branches after remote mutations. LocalGitRemoteUrl may be set
    # at the Profile level to pin the exact repository URL; otherwise it is
    # derived from RemoteHost plus the target repo.path.
    LocalRepositoryPath = ''
    LocalGitRemoteName = ''
    LocalGitRemoteUrl = ''
    BranchPrefix = 'autoresearch/'
    DefaultWorkerCount = 1
    DefaultBudgetMinutes = 30
    DefaultKeepThreshold = '0.0'
    DefaultLeaseWaitSeconds = 300

    # Generic server-side autoresearch runtime roots. Target repositories are
    # declared independently in target.yaml.
    RemoteControllerRoot = '/home/research/autoresearch-v2'
    RemoteRunRoot = '/home/research/autoresearch-v2/runs'
    RemoteWorktreeRoot = '/home/research/autoresearch-v2/worktrees'
    RemoteLeaseRoot = '/home/research/autoresearch-v2/leases'
    RemoteBridgeEntry = '/home/research/autoresearch-v2/run_autoresearch_v2_bridge.sh'
}
