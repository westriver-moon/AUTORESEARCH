@{
    ProgramPath = 'autoresearch/program.md'
    TargetPath = 'autoresearch/targets/tvilfm-stage-a.yaml'
    LocalRunRoot = 'autoresearch-runs'
    BranchPrefix = 'autoresearch/'
    DefaultWorkerCount = 1
    DefaultBudgetMinutes = 30
    DefaultKeepThreshold = '0.0'
    DefaultLeaseWaitSeconds = 300

    RemoteControllerRoot = '/home/cgv841/ybj/autoresearch-v2'
    RemoteRunRoot = '/home/cgv841/ybj/autoresearch-v2/runs'
    RemoteWorktreeRoot = '/home/cgv841/ybj/autoresearch-v2/worktrees'
    RemoteLeaseRoot = '/home/cgv841/ybj/autoresearch-v2/leases'
    RemoteBridgeEntry = '/home/cgv841/ybj/bin/run_autoresearch_v2_bridge.sh'
}
