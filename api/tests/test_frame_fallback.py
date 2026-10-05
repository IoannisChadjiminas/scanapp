from PIL import Image, ImageDraw

from app.recognition.frame_fallback import line_frame_candidates, loose_frame_candidates, portrait_window_candidates, slab_interior_candidate


def test_no_foreground_on_blank_and_no_mutation():
    image = Image.new('RGB',(500,700),'white')
    assert loose_frame_candidates(image) == []
    assert image.getpixel((0,0)) == (255,255,255)


def test_proposals_are_bounded_and_card_shaped_on_plain_background():
    image = Image.new('RGB',(500,700),'white')
    ImageDraw.Draw(image).rounded_rectangle((80,80,420,560),radius=15,fill='darkblue')
    frames = loose_frame_candidates(image,limit=2)
    assert 1 <= len(frames) <= 2
    assert all(.54 < min(f.width/f.height,f.height/f.width) < .85 for f in frames)


def test_portrait_windows_are_bounded_card_shaped_and_do_not_mutate():
    for size in ((500,500),(900,1200),(1200,500)):
        image=Image.new('RGB',size,'white')
        windows=portrait_window_candidates(image)
        assert len(windows) == 2
        assert all(abs(frame.width/frame.height - 63/88) < .01 for _,frame in windows)
        assert all(frame.width <= size[0] and frame.height <= size[1] for _,frame in windows)
        assert image.size == size
    assert portrait_window_candidates(Image.new('RGB',(50,50))) == []


def test_slab_hypothesis_requires_portrait_frame_but_does_not_claim_detection():
    assert slab_interior_candidate(Image.new('RGB',(500,500))) is None
    assert slab_interior_candidate(Image.new('RGB',(50,80))) is None
    profile, frame=slab_interior_candidate(Image.new('RGB',(300,500)))
    assert profile == 'slab_interior'
    assert abs(frame.width/frame.height - 63/88) < .01
    assert frame.width < 300 and frame.height < 500
    assert slab_interior_candidate(Image.new('RGB',(900,1200))) is not None


def test_line_proposals_bridge_broken_outline_without_mutation():
    image = Image.new('RGB',(600,800),'gray')
    draw = ImageDraw.Draw(image)
    # Four independently supported edges; disconnected corners defeat contours.
    for segment in ((120,180,480,180),(120,680,480,680),
                    (120,210,120,650),(480,210,480,650)):
        draw.line(segment,fill='white',width=3)
    before = image.tobytes()
    frames = line_frame_candidates(image)
    assert 1 <= len(frames) <= 2
    assert all(.68 < frame.width/frame.height < .76 for frame in frames)
    assert image.tobytes() == before


def test_line_proposals_reject_blank_landscape_and_single_edge():
    blank = Image.new('RGB',(600,800),'gray')
    assert line_frame_candidates(blank) == []
    assert line_frame_candidates(blank,limit=0) == []
    assert line_frame_candidates(Image.new('RGB',(80,100))) == []
    for box in ((40,300,560,650),(120,180,480,680)):
        image = blank.copy()
        draw = ImageDraw.Draw(image)
        if box[0] == 40:
            draw.rectangle(box,outline='white',width=3)
        else:
            draw.line((120,180,480,180),fill='white',width=3)
        assert line_frame_candidates(image) == []


def test_line_proposals_remain_bounded_on_large_images():
    image = Image.new('RGB',(1800,2400),'gray')
    ImageDraw.Draw(image).rectangle((300,400,1500,2080),outline='white',width=8)
    frames = line_frame_candidates(image,limit=1)
    assert len(frames) == 1
    assert frames[0].width > 1000 and frames[0].height > 1500
