@{
    # Karpathy-style bounded trial defaults. Copy to
    # config\autoresearch-train.local.psd1 for machine-specific overrides.
    RunTag = 'ar_pmt_sysu_trial'
    MetricName = 'mAP'
    Direction = 'higher'

    RemoteProjectRoot = '/home/research/researchops/PMT-SYSU'
    PythonBin = '/opt/conda/envs/research/bin/python'
    DataRoot = '/data/SYSU-MM01'
    PmtConfig = '/home/research/researchops/PMT-SYSU/pmt_sysu/config/sysu_pmt.yaml'
    Pretrained = '/home/research/researchops/PMT-SYSU/pretrained/jx_vit_base_p16_224-80ecf9dd.pth'

    Gpu = '0'
    SmokeBatches = 1
    MaxSeconds = 300

    # Full training remains outside the autoresearch loop unless separately
    # invoked through submit-job.ps1 -ConfirmFullTraining.
    AllowFullTraining = $false
}
