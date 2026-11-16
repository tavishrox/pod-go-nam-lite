# MORF-X desktop app

MORF-X ("your tone, in motion") as its own app: the MORF-X page from `web/pod-go/morph.html` in a window,
talking to the unit over USB with no browser and no device chooser. Mac first; Windows from the same project.

Units: POD Go and Helix (tested), HX Stomp and HX Stomp XL (not yet tried; Save stays hidden on them).
Quit POD Go Edit / HX Edit first: only one program can talk to the unit at a time.

    npm install
    npm start              run it from here (copies the page in from web/pod-go first)
    npm run pack-mac       dist/MORF-X-darwin-arm64 and -x64 (Apple silicon, Intel), signed ad hoc
    npm run pack-win       dist/MORF-X-win32-x64 (needs res/MORF-X.ico)
    npm run icon           remake res/MORF-X.icns and .png from web/pod-go/morf-x-icon.svg

    MORFX_SELFTEST=1 npx electron .    connect, print what MORF-X finds, disconnect, quit (reads only)

Not notarised: on a Mac other than the one it was built on, right-click the app and choose Open the first time.
