@{
    RemoteHost = 'lab-server'
    TunnelAlias = 'lab-server-codex-tunnel'
    SshConfigPath = ''
    LocalTunnelScript = ''
    ProxyTaskName = 'CodexProxyTunnelLabServer-Every5Min'

    RemoteProxyRoot = '/home/cgv841/ybj/non_research/codex_proxy'
    RemoteWorkspaceRoot = '/home/cgv841/ybj'
    RemoteAutoresearchTrialEntry = '/home/cgv841/ybj/bin/run_autoresearch_trial.sh'
    RemoteSmokeEntry = '/home/cgv841/ybj/bin/run_smoke_test.sh'
    RemoteTrainEntry = '/home/cgv841/ybj/bin/run_train.sh'
    RemoteStatusEntry = '/home/cgv841/ybj/bin/check_job.sh'
    RemoteCancelEntry = '/home/cgv841/ybj/bin/cancel_job.sh'

    ConnectTimeoutSec = 15
    ProxyPort = 7897
}
