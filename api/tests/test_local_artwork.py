import numpy as np
from PIL import Image

from app.recognition.local_match import LocalArtworkVerifier, verify_geometry


def test_local_geometry_requires_artwork_not_only_repeated_text():
    rng = np.random.default_rng(4)
    ref = rng.uniform((80, 130), (450, 320), (40, 2)).astype(np.float32)
    query = (ref - [60, 100]).astype(np.float32)
    proof = verify_geometry(query, ref, (400, 300), (500, 700))
    assert proof and proof[0] >= 14
    text_only = rng.uniform((80, 530), (450, 650), (40, 2)).astype(np.float32)
    assert verify_geometry(text_only - [60, 500], text_only, (400, 200), (500, 700)) is None


def test_geometry_rejects_sparse_degenerate_and_reflected_matches():
    rng = np.random.default_rng(5)
    ref = rng.uniform((80, 130), (450, 320), (40, 2)).astype(np.float32)
    assert verify_geometry(ref[:5], ref[:5], (500, 700), (500, 700)) is None
    reflected = ref.copy()
    reflected[:, 0] = 500-ref[:, 0]
    assert verify_geometry(reflected, ref, (500, 700), (500, 700)) is None


def test_broad_art_region_still_rejects_repeated_text_band():
    from app.recognition.local_match import FULL_ART_BOX
    rng = np.random.default_rng(6)
    text = rng.uniform((80,350),(450,380),(40,2)).astype(np.float32)
    assert verify_geometry(text-[60,200],text,(400,300),(500,700),FULL_ART_BOX) is None


def test_blank_input_never_verifies_and_paths_outside_reference_root_are_ignored(tmp_path):
    verifier = LocalArtworkVerifier(tmp_path)
    assert verifier.verify(Image.new("RGB", (500, 700), "white"), [("x", "/not/a/reference")]) == []


def test_region_hypothesis_recovers_artwork_small_in_a_full_photo(tmp_path):
    root = tmp_path / 'reference-images'
    root.mkdir()
    reference = Image.new('RGB',(500,700),'lightgray')
    patch = Image.fromarray(np.random.default_rng(10).integers(0,255,(190,380,3),dtype=np.uint8))
    reference.paste(patch,(60,133))
    path = root / 'card.png'
    reference.save(path)
    photo = Image.new('RGB',(1000,1400),'darkgray')
    photo.paste(reference,(250,320))
    matches = LocalArtworkVerifier(tmp_path).verify(photo,[('card',str(path))])
    assert len(matches) == 1 and matches[0].card_id == 'card'
    assert matches[0].query_profile != 'as_supplied'
    assert matches[0].artwork_inliers >= 14
