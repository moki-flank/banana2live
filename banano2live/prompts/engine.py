# -*- coding: utf-8 -*-
"""
banano2live 双模态实况图提示词引擎 (Dual-Engine Live Photo Prompt System)
同时支持：
  1. 【AI 视频直生转实况图 (SDK Video Generation)】：
     针对 iPhone / Android 实况照片（Live Photo / Motion Photo）的“静态封面 -> 按住微动”特性，
     强化首帧构图稳定、自然微动（发丝微风、眨眼微笑、光影流动、呼吸感）与环境原声。
  2. 【AI 宫格生图切分转实况图 (SDK 3x3 九宫格 / 4x4 十六宫格 Image Slicing)】：
     严格锁定机位、角色特征与等分白边网格，彻底消除数字角标，切分后合成为超丝滑循环实况图。
"""

from typing import Dict, Optional

# ==============================================================================
# 1. 视频直生实况图预设库 (Video-to-LivePhoto Presets)
# ==============================================================================
LIVE_VIDEO_PRESETS: Dict[str, Dict[str, str]] = {
    "breeze_portrait": {
        "title": "🍃 微风拂发 (Breeze Portrait)",
        "description": "soft breeze gently blowing through hair and clothes, natural eye blink and warm subtle smile",
        "motion": "Camera remains steady in a portrait framing; a gentle breeze softly lifts strands of hair and fabric edges, the subject blinks naturally and forms a warm, vivid smile with soft sunlight bokeh shimmering in the background.",
        "audio_hint": "soft gentle wind breeze and quiet natural ambient atmosphere",
    },
    "turn_smile": {
        "title": "✨ 回眸一笑 (Turn & Smile)",
        "description": "gently turning head toward the camera, eyes sparkling and breaking into a sweet smile",
        "motion": "Starting from a poised angle, the subject smoothly turns their head slightly toward the lens, eyes catching the light with a natural blink, followed by a radiant, authentic smile.",
        "audio_hint": "subtle rustle of clothing and warm outdoor ambient sound",
    },
    "wink_heart": {
        "title": "😉 眨眼比心 (Wink & Heart)",
        "description": "playful wink at the camera while making a cute finger heart gesture",
        "motion": "The subject looks directly into the camera, raises a hand to form a cute finger heart near the cheek, gives a playful wink with one eye, and giggles softly.",
        "audio_hint": "light cheerful ambiance",
    },
    "cafe_steam": {
        "title": "☕ 咖啡热气 (Cozy Cafe)",
        "description": "holding a warm cup of coffee with delicate steam rising, soft window light",
        "motion": "Delicate wisps of warm steam curl upward from the cup, the subject takes a gentle breath, eyes softening with a relaxed smile as golden afternoon light shifts subtly across the table.",
        "audio_hint": "quiet cozy cafe background murmur and soft ceramic clink",
    },
    "pet_tilt": {
        "title": "🐶 萌宠歪头 (Pet Head Tilt)",
        "description": "adorable pet blinking big round eyes, twitching ears, and tilting head curiously",
        "motion": "The cute pet looks straight at the lens, ears perking up and twitching softly, then tilts its head curiously to the side while blinking its bright, expressive eyes.",
        "audio_hint": "soft adorable pet breathing and gentle collar bell chime",
    },
    "cyber_rain": {
        "title": "🌧️ 霓虹雨夜 (Neon Rain)",
        "description": "cyberpunk neon reflections shimmering on wet glass, raindrops trickling down",
        "motion": "Vibrant neon reflections pulse and shimmer across rain-slicked surfaces, droplets trickle down the foreground, and cinematic volumetric mist drifts slowly around the subject.",
        "audio_hint": "gentle rain pattering and distant atmospheric city hum",
    },
    "ocean_sunset": {
        "title": "🌊 海浪微澜 (Ocean Golden Hour)",
        "description": "golden sunset waves lapping gently at the shore, hair swaying in sea breeze",
        "motion": "Sparkling golden-hour ocean waves roll gently onto the shore in the background, sea breeze softly sways the subject's hair, creating a dreamy live photo moment.",
        "audio_hint": "soothing ocean waves washing ashore and coastal breeze",
    },
}


# ==============================================================================
# 2. 宫格切分实况图预设库 (3x3 九宫格 & 4x4 十六宫格 Grid Presets)
# ==============================================================================
ACTION_PRESETS: Dict[str, Dict[str, str]] = {
    "waving": {
        "title": "👋 挥手问好 (Waving)",
        "description": "gently waving hand and smiling warmly",
        "motion_9": (
            "Panel 1: Neutral happy posture, hand resting low; "
            "Panel 2: Hand begins lifting upward slightly; "
            "Panel 3: Hand raised near shoulder level, palm open; "
            "Panel 4: Hand tilts slightly to the left, bright smile; "
            "Panel 5: Hand reaches peak wave angle to the right, joyful expression; "
            "Panel 6: Hand swings gently back to the left; "
            "Panel 7: Hand returns to center raised position; "
            "Panel 8: Hand begins lowering smoothly; "
            "Panel 9: Hand hampir back to initial resting position, matching Panel 1 for a seamless loop."
        ),
        "motion_16": (
            "Cell 1: Neutral happy posture, hand resting low; "
            "Cell 2: Hand starts lifting slightly; "
            "Cell 3: Hand rises halfway up; "
            "Cell 4: Hand reaches shoulder height, palm open; "
            "Cell 5: Hand tilts slightly left (wave 1 start); "
            "Cell 6: Hand reaches full left tilt; "
            "Cell 7: Hand passes center moving right; "
            "Cell 8: Hand reaches full right tilt, bright joyful smile; "
            "Cell 9: Hand passes center moving left again (wave 2); "
            "Cell 10: Hand reaches gentle left tilt; "
            "Cell 11: Hand swings back to gentle right tilt; "
            "Cell 12: Hand centers at shoulder level; "
            "Cell 13: Hand starts lowering smoothly; "
            "Cell 14: Hand halfway down; "
            "Cell 15: Hand almost at resting position; "
            "Cell 16: Hand returns to exact initial posture matching Cell 1 for a seamless 16-frame loop."
        ),
    },
    "breeze": {
        "title": "🍃 微风呼吸 (Live Breeze)",
        "description": "gentle wind blowing hair and clothes with natural blinking",
        "motion_9": (
            "Panel 1: Calm serene portrait, eyes open, hair resting naturally; "
            "Panel 2: Gentle breeze starts lifting hair tips slightly to the right; "
            "Panel 3: Hair flows softly in the wind, eyelids begin closing; "
            "Panel 4: Eyes softly closed in a peaceful blink, hair at mid-breeze; "
            "Panel 5: Eyes opening with a warm gentle smile, hair flowing at peak breeze; "
            "Panel 6: Bright expressive eyes, hair ribbon and strands fluttering softly; "
            "Panel 7: Breeze gradually softens, hair begins settling back; "
            "Panel 8: Hair nearly settled, warm serene smile; "
            "Panel 9: Returns smoothly to initial calm posture matching Panel 1."
        ),
        "motion_16": (
            "Cell 1: Calm serene portrait, eyes open, hair resting; "
            "Cell 2: Subtle breeze begins touching hair strands; "
            "Cell 3: Hair tips lift slightly right; "
            "Cell 4: Hair flows gently, eyelids start lowering; "
            "Cell 5: Eyes half-closed, soft smile forming; "
            "Cell 6: Eyes fully closed in a natural blink, hair swaying; "
            "Cell 7: Eyes half-open, breeze reaches peak flow; "
            "Cell 8: Eyes fully open and sparkling, warm radiant smile, hair fluttering; "
            "Cell 9: Head tilts a tiny fraction with joyful expression; "
            "Cell 10: Hair strands ripple softly in secondary breeze; "
            "Cell 11: Breeze starts easing, hair begins descending; "
            "Cell 12: Hair halfway settled, gentle breathing motion; "
            "Cell 13: Eyelids flutter slightly; "
            "Cell 14: Hair almost back to resting position; "
            "Cell 15: Expression softens to serene warmth; "
            "Cell 16: Exact initial serene posture matching Cell 1 for a seamless loop."
        ),
    },
    "wink": {
        "title": "😉 俏皮眨眼 (Wink)",
        "description": "playfully winking one eye and tilting head slightly",
        "motion_9": (
            "Panel 1: Looking forward with both eyes open and a sweet smile; "
            "Panel 2: Head starts tilting slightly, right eyelid begins lowering; "
            "Panel 3: Right eye half-closed, smile widening; "
            "Panel 4: Right eye fully closed in a cute wink, head tilted; "
            "Panel 5: Holding the playful wink at peak charm, cheerful expression; "
            "Panel 6: Right eye begins opening slightly; "
            "Panel 7: Right eye half-open, head returning toward center; "
            "Panel 8: Both eyes open, head nearly centered; "
            "Panel 9: Back to initial sweet smile posture matching Panel 1."
        ),
        "motion_16": (
            "Cell 1: Both eyes open, sweet smile; "
            "Cell 2: Head begins slight tilt; "
            "Cell 3: Right eyelid starts lowering; "
            "Cell 4: Right eye half-closed; "
            "Cell 5: Right eye 80% closed, cheek lifts; "
            "Cell 6: Right eye fully closed in a cute wink; "
            "Cell 7: Peak playful wink with tiny star-like charm; "
            "Cell 8: Holding the wink, cheerful grin; "
            "Cell 9: Wink sustained, head at peak cute tilt; "
            "Cell 10: Right eyelid begins opening slightly; "
            "Cell 11: Right eye 40% open; "
            "Cell 12: Right eye 75% open, head straightening; "
            "Cell 13: Both eyes open and bright; "
            "Cell 14: Quick natural micro-blink start; "
            "Cell 15: Eyes open again, head centered; "
            "Cell 16: Matches Cell 1 posture for a seamless loop."
        ),
    },
    "heart": {
        "title": "🫶 比心发射 (Heart Gesture)",
        "description": "making a cute heart gesture with hands and smiling sweetly",
        "motion_9": (
            "Panel 1: Hands resting near chest, sweet smile; "
            "Panel 2: Hands begin rising together; "
            "Panel 3: Fingers curving toward each other; "
            "Panel 4: Hands form a clear heart shape in front of chest; "
            "Panel 5: Peak heart pose, joyful wink and beaming smile; "
            "Panel 6: Holding the heart shape, slight cheerful bounce; "
            "Panel 7: Hands begin uncurling softly; "
            "Panel 8: Hands lowering slightly; "
            "Panel 9: Returning to initial posture near chest matching Panel 1."
        ),
        "motion_16": (
            "Cell 1: Hands resting near chest, sweet smile; "
            "Cell 2: Hands start lifting slightly; "
            "Cell 3: Hands rising toward chin level; "
            "Cell 4: Thumbs and index fingers approaching each other; "
            "Cell 5: Fingers touching to form a heart outline; "
            "Cell 6: Clear hand-heart formed, eyes brightening; "
            "Cell 7: Pushing the hand-heart slightly forward; "
            "Cell 8: Peak heart pose with a cute wink and radiant smile; "
            "Cell 9: Holding the heart pose, joyful micro-bounce; "
            "Cell 10: Both eyes open, beaming happily behind the heart; "
            "Cell 11: Hands pull back slightly toward chest; "
            "Cell 12: Fingers begin relaxing from the heart shape; "
            "Cell 13: Hands gently separating; "
            "Cell 14: Hands lowering halfway down; "
            "Cell 15: Hands nearly back at chest rest; "
            "Cell 16: Matches Cell 1 posture for a seamless loop."
        ),
    },
    "laughing": {
        "title": "😆 开心大笑 (Laughing)",
        "description": "laughing happily with shoulders bouncing gently",
        "motion_9": (
            "Panel 1: Warm smile, eyes bright; "
            "Panel 2: Mouth opens slightly into a grin, eyes curving; "
            "Panel 3: Happy laugh begins, eyes become cute curved crescents; "
            "Panel 4: Shoulders lift slightly in a joyful chuckle; "
            "Panel 5: Peak joyful laughter, radiant happy expression; "
            "Panel 6: Shoulders settle slightly while still laughing; "
            "Panel 7: Laughter softens into a wide cheerful grin; "
            "Panel 8: Eyes opening back up, mouth closing into a warm smile; "
            "Panel 9: Calm warm smile matching Panel 1."
        ),
        "motion_16": (
            "Cell 1: Warm smile, eyes bright; "
            "Cell 2: Smile widens, cheeks lift; "
            "Cell 3: Mouth opens slightly into a cheerful grin; "
            "Cell 4: Eyes curve into happy crescents; "
            "Cell 5: Shoulders lift in first laugh bounce; "
            "Cell 6: Joyful laugh, head tilts back slightly; "
            "Cell 7: Shoulders dip slightly between chuckles; "
            "Cell 8: Peak hearty laughter, beaming expression (second bounce); "
            "Cell 9: Holding the joyful laugh; "
            "Cell 10: Shoulders settle gently; "
            "Cell 11: Laughter transitions to a bright open smile; "
            "Cell 12: Eyes begin opening from crescents; "
            "Cell 13: Eyes half-open, warm grin; "
            "Cell 14: Mouth closes into a soft happy smile; "
            "Cell 15: Eyes bright and fully open; "
            "Cell 16: Matches Cell 1 posture for a seamless loop."
        ),
    },
    "crying": {
        "title": "😭 委屈哭泣 (Crying)",
        "description": "sadly crying with teardrops and wiping eyes",
        "motion_9": (
            "Panel 1: Sad pouty expression, eyes glistening with tears; "
            "Panel 2: Teardrops form at the corners of the eyes; "
            "Panel 3: Tears start rolling down cheeks, hands rising; "
            "Panel 4: Hands reach near eyes to wipe tears; "
            "Panel 5: Peak crying expression, rubbing eyes gently, tiny sob bounce; "
            "Panel 6: Hands move slightly outward while sniffling; "
            "Panel 7: Lowering hands slowly, tears subsiding; "
            "Panel 8: Hands almost down, sniffling pout; "
            "Panel 9: Back to initial sad pouty posture matching Panel 1."
        ),
        "motion_16": (
            "Cell 1: Sad pouty expression, misty eyes; "
            "Cell 2: Lower lip trembles slightly; "
            "Cell 3: Teardrops gather at eye corners; "
            "Cell 4: First teardrop rolls down the cheek; "
            "Cell 5: Both hands start lifting toward the face; "
            "Cell 6: Hands halfway up, eyes squeezing shut; "
            "Cell 7: Hands reach cheeks, wiping tears; "
            "Cell 8: Peak crying expression, rubbing eyes with a tiny sob; "
            "Cell 9: Shoulders give a small sniffle bounce; "
            "Cell 10: Second gentle rub of the eyes; "
            "Cell 11: Hands begin pulling away from face; "
            "Cell 12: Eyes opening slightly, still glistening; "
            "Cell 13: Hands lowering to chest level; "
            "Cell 14: Little sniffle, mouth in a cute pout; "
            "Cell 15: Hands nearly at resting position; "
            "Cell 16: Matches Cell 1 posture for a seamless loop."
        ),
    },
}


def build_generic_motion_flow(subject_and_action: str, action_detail: str, is_16: bool = False) -> str:
    """当未选择预设时，自动构建 9 帧或 16 帧平滑微动分镜"""
    if is_16:
        return (
            f"Cell 1: Initial poised state of {subject_and_action}; "
            f"Cells 2-4: Smoothly initiating {action_detail} with micro-increments; "
            f"Cells 5-7: Building up the motion toward its natural midpoint; "
            f"Cells 8-9: Reaching the expressive peak of {action_detail}; "
            f"Cells 10-12: Smoothly transitioning back from the peak; "
            f"Cells 13-15: Gradually settling back toward the initial pose; "
            f"Cell 16: Returning to the exact starting posture of Cell 1 for a seamless loop."
        )
    return (
        f"Panel 1: Initial poised state of {subject_and_action}; "
        f"Panels 2-3: Smoothly initiating {action_detail}; "
        f"Panels 4-5: Reaching the natural expressive peak of {action_detail}; "
        f"Panels 6-8: Smoothly easing back toward the neutral pose; "
        f"Panel 9: Returning to the exact starting posture of Panel 1 for a seamless loop."
    )


def build_video_live_prompt(
    subject_and_action: str,
    preset: Optional[str] = None,
    style: str = "Cinematic live photo, ultra-high definition, natural lighting, shallow depth of field, authentic texture",
    has_reference_image: bool = False,
    has_last_frame: bool = False,
) -> str:
    """
    构建专为 AI 视频直生转实况图 (SDK Video-to-LivePhoto) 优化的提示词。
    重点强调：首帧高颜值定格、镜头稳定微动、逼真物理细节（发丝/光影/呼吸）与自然环境声。
    """
    preset_info = LIVE_VIDEO_PRESETS.get(preset or "", None)
    motion_detail = preset_info["motion"] if preset_info else (
        f"Subtle, lifelike continuous motion: {subject_and_action}. "
        "Natural breathing, gentle hair and fabric movement, expressive eye blink, and soft ambient light shifts."
    )
    audio_detail = preset_info["audio_hint"] if preset_info else "natural subtle ambient sound matching the scene, no artificial background music"

    ref_instruction = ""
    if has_reference_image and has_last_frame:
        ref_instruction = (
            "FIRST-TO-LAST FRAME LIVE PHOTO TRANSITION: Start seamlessly from the exact composition and character appearance of the first reference image, "
            "and transition smoothly and naturally into the pose of the final reference image. "
        )
    elif has_reference_image:
        ref_instruction = (
            "IMAGE-TO-LIVE-PHOTO CONSISTENCY: Start from the exact composition, lighting, and character identity of the reference image. "
            "Preserve facial features, outfit, and background strictly while bringing the moment to life with natural micro-motion. "
        )

    prompt = (
        f"High-resolution Live Photo moment (3 to 5 seconds): {subject_and_action}. "
        f"{ref_instruction}"
        f"MOTION & CAMERA: Steady handheld or tripod portrait framing with zero jarring cuts. {motion_detail} "
        f"AUDIO: {audio_detail}. "
        f"NEGATIVE CONSTRAINTS: No text, no subtitles, no watermarks, no logos, no sudden camera cuts, no morphing artifacts. "
        f"STYLE: {style}."
    )
    return prompt


def build_grid_live_prompt(
    subject_and_action: str,
    preset: Optional[str] = None,
    grid: str = "3x3",
    style: str = "High-end 3D animation render, soft ambient lighting, clean solid pastel studio background, Pop Mart collectible figurine style",
    custom_motion: Optional[str] = None,
    has_reference_image: bool = False,
    is_4k: bool = False,
) -> str:
    """构建专为 3x3 九宫格 / 4x4 十六宫格切分转实况图优化的提示词"""
    is_16 = "4" in str(grid) or str(grid) == "16"
    panel_count = 16 if is_16 else 9
    layout_desc = (
        "4x4 animation contact sheet sprite grid consisting of exactly 16 equal square panels arranged in 4 rows and 4 columns"
        if is_16
        else "3x3 animation contact sheet grid consisting of exactly 9 sequential square panels"
    )

    if custom_motion:
        motion_desc = custom_motion
    elif preset and preset in ACTION_PRESETS:
        p = ACTION_PRESETS[preset]
        subject_and_action = f"{subject_and_action}, {p['description']}"
        motion_desc = p["motion_16"] if is_16 else p["motion_9"]
    elif preset and preset in LIVE_VIDEO_PRESETS:
        vp = LIVE_VIDEO_PRESETS[preset]
        subject_and_action = f"{subject_and_action}, {vp['description']}"
        motion_desc = build_generic_motion_flow(subject_and_action, vp["description"], is_16=is_16)
    else:
        motion_desc = build_generic_motion_flow(subject_and_action, "the smooth looping live photo motion", is_16=is_16)

    reference_anchor = ""
    if has_reference_image:
        reference_anchor = (
            "REFERENCE CHARACTER LOCK: Maintain exact, strict identity consistency with the character/subject in the provided reference image. "
            "Preserve identical facial features, eye shape, hairstyle, hair color, clothing style, key accessories, and aesthetic identity across all panels. "
        )

    resolution_tag = ", ultra high resolution 4K UHD, 4096x4096 resolution, extremely sharp fine details, 8k render, masterpiece" if is_4k else ""
    order_guide = (
        "Row 1 (top row) left-to-right, Row 2 left-to-right, Row 3 left-to-right, Row 4 (bottom row) left-to-right"
        if is_16
        else "Top row left-to-right, Middle row left-to-right, Bottom row left-to-right"
    )

    prompt = (
        f"A clean {layout_desc} showing ONE continuous, ultra-smooth Live Photo micro-motion cycle: "
        f"{reference_anchor}"
        f"{subject_and_action}. "
        f"CRITICAL MOTION RULES: "
        f"1. LOCKED CAMERA: Absolutely static camera, identical distance, identical zoom, consistent background. The main body of the character stays in the exact same physical coordinates across all {panel_count} panels. "
        f"2. SEQUENTIAL PROGRESSIVE MICRO-MOTION FLOW (Spatial Order: {order_guide}): "
        f"{motion_desc} "
        f"LAYOUT: Equal {'4x4' if is_16 else '3x3'} grid separated by thin, clean, solid white borders. "
        f"STRICT NEGATIVE CONSTRAINT: ABSOLUTELY NO numbers, NO digits, NO frame index watermark (such as 01, 02... 16, 1, 2... 16), NO text, NO labels, NO logos, NO captions anywhere in the image. Every panel must contain 100% pure visual artwork. "
        f"STYLE: {style}{resolution_tag}."
    )
    return prompt


# 兼容别名
build_prompt = build_grid_live_prompt


def build_motion_transfer_prompt(
    action_hint: str = "transfer the exact motion and poses from the motion guide to the target character",
    grid: str = "3x3",
    style: str = "Preserve target character art style, high quality render, clean solid studio background",
    is_4k: bool = False,
) -> str:
    """动作迁移专用提示词（支持 3x3 与 4x4 双参考图）"""
    is_16 = "4" in str(grid) or str(grid) == "16"
    panel_count = 16 if is_16 else 9
    layout_name = "4x4" if is_16 else "3x3"
    resolution_tag = ", ultra high resolution 4K UHD, 4096x4096, extremely sharp fine details, 8k render, masterpiece" if is_4k else ""

    prompt = (
        f"A clean {layout_name} animation contact sheet grid consisting of exactly {panel_count} sequential square panels. "
        f"DUAL REFERENCE MOTION TRANSFER TASK: "
        f"1. TARGET CHARACTER REFERENCE (Image 1): Strictly preserve the exact appearance, face, eyes, hair color, hairstyle, costume, and art style of the character in Image 1. "
        f"2. MOTION & POSE SEQUENCE GUIDE (Image 2): Image 2 is a {layout_name} motion sheet showing a {panel_count}-frame animation cycle. "
        f"Strictly mirror and transfer the EXACT same progressive body posture, hand gestures, facial expression shifts, and motion timing from Image 2 onto the target character from Image 1, cell by cell (reading left-to-right, top-to-bottom across all {panel_count} cells). "
        f"Action focus: {action_hint}. "
        f"LOCKED CAMERA: Completely static camera, identical distance and zoom, solid clean background, seamless infinite loop from last cell back to first cell. "
        f"LAYOUT: Equal {layout_name} grid separated by thin, clean, solid white borders. "
        f"STRICT NEGATIVE CONSTRAINT: ABSOLUTELY NO numbers, NO digits, NO frame index watermark (such as 01, 02... 16, 1, 2... 16), NO text, NO labels, NO logos. Every panel must contain 100% pure visual artwork. "
        f"STYLE: {style}{resolution_tag}."
    )
    return prompt
