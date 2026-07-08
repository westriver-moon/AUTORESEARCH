@{
    SkillPath = '.agents\skills\codex-autoresearch-v2'
    DevSkillPath = '.agents\skills\codex-autoresearch-v2-dev'
    RuntimeEntry = 'scripts\remote\autoresearch-v2.ps1'
    SmokeEntry = 'scripts\remote\smoke-autoresearch-v2.ps1'
    ModeGuardEntry = 'scripts\remote\guard-autoresearch-mode.ps1'
    GitHookEntry = '.githooks\pre-commit'

    Invocation = 'explicit_only'
    SessionMode = 'invoke'
    DevelopmentMode = 'develop'
    ResultsDirectory = 'autoresearch-runs'
    PythonCommand = 'python'
    PackagedPlugin = 'plugins\codex-autoresearch-v2'

    SealedPaths = @(
        '.agents\skills\codex-autoresearch-v2\**',
        'scripts\remote\guard-autoresearch-mode.ps1',
        'scripts\remote\autoresearch-v2.ps1',
        'scripts\remote\smoke-autoresearch-v2.ps1',
        'scripts\remote\lib\common.ps1',
        'scripts\remote\lib\ssh.ps1',
        'scripts\remote\lib\result.ps1',
        'scripts\remote\lib\paths.ps1',
        'scripts\remote\lib\autoresearch_v2.ps1',
        'scripts\remote\remote-bin\autoresearch_v2_*.py',
        'scripts\remote\remote-bin\run_autoresearch_v2_bridge.sh',
        'plugins\codex-autoresearch-v2\**'
    )

    RequireGitRepo = $true
    AllowBackgroundWorkers = $true
    AllowExec = $false
    AllowHooks = $false
    AllowFullAccessBypass = $false
    AllowDangerouslyBypassApprovalsAndSandbox = $false
    AllowSshDuringSkillLaunch = $false
    AllowGpuDuringSkillLaunch = $false
}
