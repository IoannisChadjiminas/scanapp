"""API-only deployment atop speed029; opt-in card scheduling and progress.

Preserves the exact currently active catalogue/environment/resource limits and
freezes the current compose chain. Rollback uses a pinned current image.
"""
import activate_speed029_staging as guarded

guarded.IMAGE = 'scanapp-speed030-api:20261004'
guarded.BASE = 'sha256:3118fbc52b108eb5322a353e45996a2b9a6b582df876d9969bdee5910687c03e'
guarded.CONFIG_HASH = '0309f27ae3188936d718c81943a65007f2d3c2bde138266f6b9982e13b48d8cf'
guarded.RELEASE = 'speed030'
guarded.OVERRIDE_ENV = {'OCR_PARALLEL_FOOTER_HALVES': '1',
                        'OCR_CARD_PRIORITY': '1', 'SCAN_STREAM_ENABLED': '1'}
# The staged-original experiment remains disabled until a measurable benefit
# and an unchanged matching contract have both been established.
guarded.EXPECTED = {
    'ocr.py': 'efee28997b92f8ec2d63fb564d8d937861d69d239c8e23ee5ef0e5a5a089060b',
    'auxiliary_work.py': '6adbce71f9c8f88ed75e4cc987883a734fe531ea5cd55ac2cc43a23533cbdfc3',
    'runtime.py': 'e82d3b3f3e81ca98e29a527b4e7fcf6658fadbb2177107d5e3ed4b784069cd65',
    'ocr_framing.py': '3e0348600fc311bf5850588c462ea17adf14c963729c1173512c407397d5f37f',
    'pipeline.py': '641fd02a65d8c401c3676fa1f5514c26017044ba1c69d117a6799352c430c764',
}
guarded.EXTRA_HASHES = {
    'app/main.py': '2860b09b817eaef64a855dbcf5a3f295de77ecd3c17a2a8c4ad3e4386fa878da',
    'app/routes/scans.py': '11636064055764fb27ec642bf9fa8070789623955c7a6fad71bf4c8d331a95fa',
}

if __name__ == '__main__': guarded.main()
