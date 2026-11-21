# Bundled Khmer subtitle font

`KantumruyPro.ttf` is the variable-weight Kantumruy Pro font by the Kantumruy Pro
Project Authors. It is licensed under the SIL Open Font License 1.1 (see
`OFL.txt`).

The backend copies this font next to the render and passes `FontName=Kantumruy Pro`
to FFmpeg/libass. This ensures burned Khmer subtitles render correctly even when
the font is not installed system-wide.
