@{
    RemoteHost = 'your-gpu-host'
    TunnelAlias = 'your-gpu-host-codex-tunnel'
    SshConfigPath = ''
    LocalTunnelScript = ''
    ProxyTaskName = 'CodexProxyTunnelGpuHost-Every5Min'

    RemoteProxyRoot = '/home/research/researchops/non_research/codex_proxy'
    RemoteWorkspaceRoot = '/home/research/researchops'
    RemoteSmokeEntry = '/home/research/researchops/bin/run_smoke_test.sh'
    RemoteTrainEntry = '/home/research/researchops/bin/run_train.sh'
    RemoteStatusEntry = '/home/research/researchops/bin/check_job.sh'
    RemoteCancelEntry = '/home/research/researchops/bin/cancel_job.sh'

    ConnectTimeoutSec = 15
    ProxyPort = 7897
}
