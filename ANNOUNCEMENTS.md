# Posts to send

Local drafts. Nothing here has been posted.

Hold all three until the repository is public. This commit is only on this machine, and there is no GitHub remote yet. Replace every `[repo URL]` with the real link. Attach the stills in this order, then a few seconds of the amulet turning if you have the clip:

![Day](screenshots/day.png)

![Halfway](screenshots/mid.png)

![Night](screenshots/night.png)

The album link is live now: https://store.steampowered.com/app/2550490/Sea_of_Stars__OST/

---

## 1. Social post

Use this on your own account. It is short enough for a standard post.

```
Unofficial player for the Sea of Stars soundtrack. Day and Night stay on the same beat. Turn the amulet and only the volume moves. It plays your Steam copy.

https://store.steampowered.com/app/2550490/Sea_of_Stars__OST/
[repo URL]
```

Attach these stills in this order.

![Day. The amulet sits at the sun.](screenshots/day.png)

![Halfway. Day and night are even.](screenshots/mid.png)

![Night. The amulet sits at the moon.](screenshots/night.png)

---

## 2. Sabotage Studio Discord

Server: https://discord.gg/sabotagestudio

Put this in the channel they use for fan art and fan projects. Leave the studio untagged.

```
Hey. I made an unofficial player for the day and night pairs on the Sea of Stars soundtrack.

In the game, once you have the Solstice Amulet, outdoor songs keep both arrangements running and only the volumes move. This does the same thing with the files from Sea of Stars - OST. You turn the amulet from Day toward Night and both stems stay on the same beat. The window fades with the mix.

The music is not included. It reads the album Steam already installed:
https://store.steampowered.com/app/2550490/Sea_of_Stars__OST/

I am not with Sabotage, and the pictures are fan paintings rather than game assets. The code is MIT.

[repo URL]
```

Attach the same three stills, in the same order.

![Day. The amulet sits at the sun.](screenshots/day.png)

![Halfway. Day and night are even.](screenshots/mid.png)

![Night. The amulet sits at the moon.](screenshots/night.png)

---

## 3. Steam Community guide

Post this on the Sea of Stars - OST community guides:
https://steamcommunity.com/app/2550490/guides/

Title:

```
Play the day and night arrangements together
```

Paste this, then upload the three stills in order.

```
Unofficial fan player. Not made or endorsed by Sabotage Studio.

Solstice Amulet plays a day arrangement and its night arrangement on the same beat. You turn the amulet and the two volumes crossfade. The painted window follows the same mix. That is the outdoor swap from the game, once the Solstice Amulet is unlocked: both versions keep running, and only the loudness moves.
```

![Day. The amulet sits at the sun.](screenshots/day.png)

![Halfway. Day and night are even.](screenshots/mid.png)

![Night. The amulet sits at the moon.](screenshots/night.png)

Paste the rest under the pictures.

```
You need your own copy of the album. The player does not download music.

Sea of Stars - OST
https://store.steampowered.com/app/2550490/Sea_of_Stars__OST/

The game is a separate purchase:
https://store.steampowered.com/app/1244090/Sea_of_Stars/

How to run it

The player is a Python program. You need Python 3.11 or newer.

1. Download the project: [repo URL]
2. In that folder, run: pip install -r requirements.txt
3. Run: python player.py

It looks in the usual Steam music folder:

C:\Program Files (x86)\Steam\steamapps\music\Sea of Stars - OST

If your album lives somewhere else:

python player.py --library "D:\Music\Sea of Stars - OST"

Controls

Drag the amulet from Day toward Night and let go wherever you want the mix. The wheel and the arrow keys nudge it. The Day and Night labels ease the rest of the way to that side. Space plays and pauses. Up and down change tracks. The bar under the title seeks both arrangements together.

The list is the day/night pairs only. Credits in the menu are Eric W. Brown, Yasunori Mitsuda, Vincent Jones, and Reece Miller.

The code is MIT. The paintings in the window are fan art, and the soundtrack stays with its owners.
```
