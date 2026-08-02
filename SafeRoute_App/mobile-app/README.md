# SafeRoute mobile

Expo SDK 57 / React Native 0.86 mobile client for the SafeRoute staging API.
The app uses native Mapbox, Supabase Auth, GPS, turn-by-turn navigation and
Turkish text-to-speech. Use a development build; Expo Go cannot load the native
Mapbox module.

## Local checks

```powershell
npm ci --legacy-peer-deps
npm run typecheck
npm run lint
npm test -- --runInBand
```

Runtime public configuration belongs in `.env.local`; use `.env.example` as the
template. `EXPO_PUBLIC_*` values are embedded in the client and are not secrets.
`MAPBOX_DOWNLOAD_TOKEN` is private build-time configuration and belongs in the
local ignored env file or EAS secrets. A Supabase service-role key must never be
placed in the mobile project.

For an Android phone connected over USB, follow
[`docs/runbooks/physical_android_testing.md`](../../docs/runbooks/physical_android_testing.md)
from the repository root. The provided USB script overrides the placeholder
backend URL for that process and tunnels ports 8002 and 8081 with `adb reverse`.

## Build profiles

`eas.json` provides `development`, `preview` and `production` profiles. A
production build fails early when required public values or the Mapbox download
token are missing. iOS builds require EAS/macOS and the configured bundle ID;
Android uses package `com.saferoute.mobileapp`.
