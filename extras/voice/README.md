# voiceforge

> ⚠ **Proof of concept, written by Claude (AI) – no warranty, use at your own risk.** See [Disclaimer](#disclaimer).

Voice changer and soundboard for **Linux with PipeWire** (Fedora's default). voiceforge adds a
virtual microphone – **VoiceForge Microphone** – that you pick as input in Discord, Vesktop, CS2,
OBS or anything else. Your voice goes through the effect you choose, and soundboard sounds are
mixed in on top.

```
your microphone ──► effect (deep, chipmunk, robot, radio, echo, cave …) ──┐
                                                                           ├──► VoiceForge Microphone
soundboard (.wav .ogg .flac .mp3 .opus) ───────────────────────────────────┘
```

- **11 voices:** clean (noise gate only), deep, chipmunk, robot, radio, megaphone, echo, cave,
  alien, demon, custom pitch (−12 … +12 semitones) – switch live, mid-sentence
- **Soundboard:** any audio file, keys 1–9, stop all with 0; you can hear the sounds yourself too
- **Hotkeys in Sway:** Super+Alt+1…9 play, Super+Alt+0 stops, Super+Alt+V next voice,
  Super+Alt+Shift+V back to your normal voice
- **Never feeds back:** it always listens to your real microphone, never to itself
- **Leaves no traces:** the virtual devices are created on start and removed on stop; nothing is
  installed system-wide, nothing leaves your PC
- Six starter sounds made from scratch (air horn, sad trombone, ba dum tss …) – no copyright worries

> Using [swayforge](https://github.com/Diesumpfeule/swayforge)? Tick *voiceforge* in its installer
> (Own tools): it installs voiceforge, colours the app in your theme and loads the hotkeys.

## Install

```bash
git clone https://github.com/Diesumpfeule/voiceforge
cd voiceforge
bash install.sh
```

It installs what's missing (`python3-numpy`, `python3-textual`, `pipewire-utils`,
`pulseaudio-utils`) with dnf and puts the `voiceforge` command into `~/.local/bin`.

## Use

```
voiceforge                 the app: pick a voice, play sounds, switches
voiceforge start           virtual microphone on (runs in the background)
voiceforge stop            off – the virtual microphone disappears
voiceforge effect deep     clean | deep | chipmunk | robot | radio | megaphone | echo | cave |
                           alien | demon | custom | next | previous
voiceforge play 3          sound number 3 (or a file path)
voiceforge hush            stop all sounds
voiceforge list            your sounds
voiceforge status
voiceforge keys            write the Sway hotkeys file
```

Then select **VoiceForge Microphone** as input device:
- **Discord / Vesktop:** *Settings → Voice & Video → Input device*. Switch off *Noise suppression*
  and *Automatic gain control* there – they would fight the effects.
- **CS2 / Steam games:** Steam uses the system default input – set *VoiceForge Microphone* as
  default in your sound settings (e.g. `pactl set-default-source voiceforge_mic`) while you play.
- **OBS:** add an *Audio Input Capture* with *VoiceForge Microphone*.

**Your own sounds:** put files into `~/.local/share/voiceforge/sounds` (the app's *Sounds folder*
button opens it). They are numbered in alphabetical order – start names with `01 `, `02 ` … to
choose the hotkey.

**Hear yourself:** *Hear my changed voice* in the app plays the result on your headphones (about
40 ms delay – use headphones, speakers would echo).

## How it works

`voiceforge start` creates two PipeWire devices with `pactl`: an internal sink *VoiceForge-Mix*
and, on top of its monitor, the source *VoiceForge Microphone*. A small engine reads your real
microphone with `pw-record` in 20 ms blocks, runs the effect with numpy and plays the result into
the mix with `pw-play`; soundboard sounds are played into the same mix. The effects are classic
real-time DSP: a two-tap delay-line pitch shifter, ring modulation, FIR band-pass filters,
soft clipping, a feedback echo and FFT convolution reverb. Every effect needs a few milliseconds
per block at most.

Settings live in `~/.config/voiceforge/config.json` (the running engine follows changes within a
fifth of a second), the log in `~/.cache/voiceforge.log`.

## Troubleshooting

- **No “VoiceForge Microphone” in Discord** – is it running (`voiceforge status`)? Restart
  Discord after the first start; some apps only read the device list when they open.
- **Others hear nothing** – `voiceforge status` shows which microphone is used; *Microphone …*
  in the app switches between your inputs.
- **Robotic crackling** – the PC is too busy for 20 ms blocks; close heavy apps or use *clean*.

## Uninstall

`bash uninstall.sh` (your sounds and settings stay) or `bash uninstall.sh --all`.

## Disclaimer

**This is a proof of concept** – not finished, not polished and not tested on every setup.
The code was written by **Claude**, an AI model by Anthropic, following my ideas and
instructions. It is provided **as is, without any warranty**, and I take **no responsibility**
for anything it does to your system, your data or your accounts. Read the scripts before you
run them – use at your own risk. Don't use a changed voice to deceive or harass people.

## Contributions

This is a personal project: pull requests and outside code are not accepted. Feel free to fork it.

## License

MIT – see [LICENSE](LICENSE).
