@{
    SkillPath = '.agents\skills\codex-autoresearch'
    VendorPath = '.agents\vendor\codex-autoresearch-windows-skill'
    LockFile = 'THIRD_PARTY_SKILLS.lock.yml'

    Invocation = 'explicit_only'
    SessionMode = 'foreground'
    ResultsDirectory = 'autoresearch-results'
    PythonCommand = 'python'

    RequireGitRepo = $true
    AllowControlledRemoteTrialBridge = $true
    AllowFullTrainingFromAutoresearch = $false
    AllowImplicitInvocation = $false
    AllowBackground = $false
    AllowExec = $false
    AllowHooks = $false
    AllowFullAccessBypass = $false
    AllowDangerouslyBypassApprovalsAndSandbox = $false
    AllowSshDuringSkillLaunch = $false
    AllowGpuDuringSkillLaunch = $false

    ForbiddenRuntimeArtifacts = @(
        'launch.json',
        'runtime.json',
        'runtime.log'
    )
}
