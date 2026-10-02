# Solstice Amulet — Sea of Stars day/night player

A small player that switches a Sea of Stars track between its Day and Night masters the way the game does: both arrangements stay running on one clock, and only their volumes move.

## How the game mixes Day and Night

Primary source: Sabotage’s Audiokinetic post, [Sea of Stars: Modern Tools for Retro Aesthetics](https://www.audiokinetic.com/en/blog/sea-of-stars-modern-tools-for-retro-aesthetics/). Day and night are not an automatic cycle. Once the Solstice Amulet is unlocked, the player swaps time of day at will.

Outdoor music is a pair of arrangements that share a core structure (same form, same tempo grid) and differ in writing: more bells, quieter tone, or a half-time feel at night. Eric W. Brown has described the standard battle pair the same way — the night chart is the day chart with bells and small rearrangements ([Game Informer, 24 Mar 2023](https://www.gameinformer.com/exclusive/2023/03/24/diving-deep-into-sea-of-stars-nostalgic-soundtrack)).

The mix that makes the swap seamless:

- Both the Day stem and the Night stem are playing at all times, in parallel, locked to the same timeline.
- A Wwise volume RTPC (a real-time parameter tied to in-game time of day) holds Night at silence during the day, and Day at silence during the night.
- Changing time of day moves that parameter, so one voice rises while the other falls. The melody and the drums never jump to a new bar, because the silent stem was already on that beat.

That is a volume crossfade of two synced streams. It is not a playlist skip, not a timestretch, and not an EQ curve applied to a single recording. The timbre change is already baked into the Night arrangement.

A separate filter trick exists and should stay out of this plugin. In battle, Brown recreates the SNES eight-voice limit by briefly muting the drum bus when a hit or a spell needs the channel ([Time Extension, 21 Feb 2023](https://www.timeextension.com/news/2023/02/sea-of-stars-composer-shares-snes-homage-hidden-within-games-audio)). That filter follows sound effects. It is not the solstice swap.

The published write-up does not give a ramp length or a curve. What it does say is that the volume parameter is linked to the in-game time of day, and time of day is something the player scrolls with the triggers after the amulet is found. The sky can sit anywhere between the two extremes, so the two volumes can sit anywhere too. In this player the amulet is that scroll. Drag it left toward Day or right toward Night and both volumes stay wherever you let go, on the same sample. The ring turns with it: left at Day, right at Night. The wheel and the arrow keys nudge the same control. The Day and Night marks ease the rest of the way.

Wwise’s `SetRTPCValue` interpolates linearly unless the call asks for another curve, and Voice Volume itself is in decibels. Sabotage did not publish which of those they used. For two full mixes that already share a beat, equal-power in amplitude holds the loudness steadier than a straight line:

```
t goes from 0 (day) to 1 (night)
day   = cos(t * π/2)
night = sin(t * π/2)
```

At either end one gain is 1 and the other is 0. Dragging, the wheel, and the arrow keys set `t` directly. A full ease from the Day or Night mark takes about **1.8 s**, scaled to the distance left to travel. That number is a stand-in, not a measured sky scroll. The same `t` drives the plates and the amulet's turn. Pause freezes an ease that has already started.

Pirate / bardcore charts are a third written arrangement used when the story calls for it. They are not a third layer under the amulet. Leave them out of the first version.

## Why this is not a VLC skin file

A VLC skin (`.vlt`, Skins2 XML plus bitmaps) draws the window. It cannot open a second decoder or ramp two gains.

A Lua extension can drive the playlist and pop a dialog. It cannot mix two files on one sample clock. VLC 3 also has no playlist crossfade, and a crossfade between playlist items would restart the other arrangement at bar 1 anyway.

Driving two `vlc.exe` processes over the RC interface (the approach used by tools like vlcsync) wanders by up to about half a second. That is enough to flam the drums. On Windows, two players created from one libVLC instance have also been reported to share a single volume ([LibVLCSharp #451](https://code.videolan.org/videolan/LibVLCSharp/-/issues/451)).

So the player is a small host with two decoders, not a `.vlt` dropped into VLC’s skin folder. A skin still cannot park a mix between two files, and it cannot turn the amulet on that same clock. The window can still look like a VLC skin. The amulet is the only control that matters.

## Playback rules

1. Resolve a pair, then start both decoders at position 0. The inactive gain stays at 0. Both keep decoding while one is silent, which is what lets the next swap land on the same beat.
2. Play, pause, and seek hit both decoders with the same target time. Seek clamps each side to its own duration.
3. The ramp uses the audio clock, so pause freezes a fade halfway.
4. Loop the pair together. OST masters are not the Wwise loop segments. Published lengths already disagree by about a second on some pairs (Mooncradle 2:21 vs 2:23, Celestial Quandary 4:03 vs 4:01, The Frozen Peak 4:09 vs 4:11). Mountain Trail matches at 3:24. Do not timestretch. Loop point is the shorter duration: when the short side ends, seek both back to 0. That drops a short tail instead of letting the next loop drift.
5. One output device mixes both stems. Decode the mp3 masters and resample to 48 kHz so a 44.1 kHz file stays on the same clock.

## Library and pairing

The Steam folder has four discs, each as mp3 and wav (253 of each). The player reads the mp3s. Names do not use parentheses. After the track-number prefix, the suffix is `_Day` or `_Night`:

```
01-003_The_Mountain_Trail_Day.mp3
02-01_The_Mountain_Trail_Night.mp3
```

The key is that stem with the suffix removed, compared case-insensitively. `Battle On` is the one day file with no `_Day` suffix; it pairs with `Battle_On_Night`. That match makes 19 pairs. Everything else plays as a single file, with the amulet disabled.

Six pairs are the same length at 48 kHz, including The Mountain Trail (204.62 s both). The widest gap is The Lost Village of Docarri, whose night master runs 4.36 s longer. Through The Jungle’s night file is 44.1 kHz while the day file is 48 kHz. Loop at the shorter length after resampling. Do not timestretch.

## Skin

The Glacial Peak shot at `digitaltq` is a 600×338 WebP. The amulet in the ice is only a few pixels wide: a thick gold ring with a dark center, sitting in the crystal above Zale and Valere. These icons are a crisp read of that sprite, with a sun or a moon drawn into the center so the button shows which arrangement is audible.

Valere and Zale stand in the window behind that button, taken from the pose in the 2021 key art (Valere kneeling in front with the crescent staff, Zale just behind her with the sun-flame sword). Two plates share that pose:

- Day: warm sun in the sky, Zale’s flame up, the islands in afternoon light.
- Night: the moon in the same place in the sky, Valere’s staff brighter, the islands in moonlight.

The picture crossfades with the music. The same ramp that moves the two audio gains moves the two plate opacities, so at the midpoint the sun sits inside the moon and both heroes are still one figure. Poses match on purpose. If they walked or swapped places, the fade would ghost into two pairs of characters.

The playlist and the amulet sit along the bottom, over the cliff, so they do not cover their faces. The playlist is the pair list, drawn in the same ink and gold. The amulet uses the same ramp as the music: sun face, moon face, and both at once in between, while the ring leans left at Day and right at Night.

| File | Role |
| --- | --- |
| `skin/amulet-rest.png` | The ring as it sits in the ice. Idle / unpaired. |
| `skin/amulet-day.png` | Day gain at 1. |
| `skin/amulet-night.png` | Night gain at 1. |
| `skin/bg-day.jpg` | Day plate, 1600×800. |
| `skin/bg-night.jpg` | Night plate, 1600×800. |
| `skin/bg-mid.jpg` | Equal-power midpoint of the two plates. |
| `skin/preview-day.png` | Window study, day. |
| `skin/preview-night.png` | Window study, night. |
| `skin/preview-mid.png` | Window study, halfway through the ramp. |

The amulet icons are 256×256 with a transparent background. Dragging the amulet parks the mix. The Day and Night marks ease to that end. The window shows the paired title with the suffix stripped, and how far the dial sits between the two.

## First build

One window. One folder. A list of pair titles in the playlist panel. Transport (play, pause, seek, loop) on the shared clock. The amulet dial sets the two audio gains and the two background plates, and turns as it does. No equalizer, no pirate charts, no VLC skin package until the mix is right.
