@{
    # Remote training defaults. Copy to
    # config\autoresearch-train.local.psd1 for machine-specific overrides.
    RunTag = 'ar_tvilfm_pmtvit_stagea_trial'
    MetricName = 'mAP'
    Direction = 'higher'

    RemoteProjectRoot = '/home/research/researchops/TVI-LFM'
    PythonBin = '/opt/conda/envs/tvi-lfm/bin/python'
    DataRoot = '/data/SYSU-MM01'
    PmtConfig = '/home/research/researchops/TVI-LFM/config/stage_a/pmt_vit_stage_a_current_best.yaml'
    # Optional local mirror of PmtConfig used for local epoch inspection before
    # launching a human-confirmed remote training job.
    LocalConfigPath = ''
    Pretrained = '/home/research/researchops/PMT-SYSU/pretrained/jx_vit_base_p16_224-80ecf9dd.pth'

    # Use a concrete GPU id such as '0', or 'auto' to let the fixed remote
    # entrypoint pick an idle GPU with nvidia-smi before launching.
    Gpu = 'auto'
    SmokeBatches = 1
    MaxSeconds = 300
    AllowBoundedTraining = $true
    MaxAutoEpochs = 50

    # Training above MaxAutoEpochs remains outside the autoresearch loop unless
    # separately invoked through submit-job.ps1 -ConfirmFullTraining.
    AllowFullTraining = $false
}
