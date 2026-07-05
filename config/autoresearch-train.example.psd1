@{
    # Karpathy-style bounded trial defaults. Copy to
    # config\autoresearch-train.local.psd1 for machine-specific overrides.
    RunTag = 'ar_pmt_sysu_trial'
    MetricName = 'mAP'
    Direction = 'higher'

    RemoteProjectRoot = '/home/cgv841/ybj/PMT-SYSU'
    PythonBin = '/home/cgv841/anaconda3/envs/reid/bin/python'
    DataRoot = '/home/cgv841/datasets/SYSU-MM01'
    PmtConfig = '/home/cgv841/ybj/PMT-SYSU/pmt_sysu/config/sysu_pmt.yaml'
    Pretrained = '/home/cgv841/ybj/PMT-SYSU/pretrained/jx_vit_base_p16_224-80ecf9dd.pth'

    Gpu = '0'
    SmokeBatches = 1
    MaxSeconds = 300

    # Full training remains outside the autoresearch loop unless separately
    # invoked through submit-job.ps1 -ConfirmFullTraining.
    AllowFullTraining = $false
}
