// Map our env var name onto the one @rnmapbox/maps now expects, so the
// (native) build picks up the download token without the deprecated
// `RNMapboxMapsDownloadToken` plugin option.
process.env.RNMAPBOX_MAPS_DOWNLOAD_TOKEN = process.env.MAPBOX_DOWNLOAD_TOKEN;

export default {
  "expo": {
    "name": "mobile-app",
    "slug": "mobile-app",
    "version": "1.0.0",
    "orientation": "portrait",
    "icon": "./assets/images/icon.png",
    "scheme": "mobileapp",
    "userInterfaceStyle": "automatic",
    "ios": {
      "icon": "./assets/expo.icon",
      "bundleIdentifier": "com.saferoute.mobileapp",
      "infoPlist": {
        "ITSAppUsesNonExemptEncryption": false,
        "NSLocationWhenInUseUsageDescription": "SafeRoute uses your location to center the map on you and find the safest route from where you are."
      }
    },
    "android": {
      "adaptiveIcon": {
        "backgroundColor": "#E6F4FE",
        "foregroundImage": "./assets/images/android-icon-foreground.png",
        "backgroundImage": "./assets/images/android-icon-background.png",
        "monochromeImage": "./assets/images/android-icon-monochrome.png"
      },
      "predictiveBackGestureEnabled": false,
      "package": "com.saferoute.mobileapp"
    },
    "web": {
      "output": "static",
      "favicon": "./assets/images/favicon.png"
    },
    "plugins": [
      "expo-router",
      [
        "expo-splash-screen",
        {
          "backgroundColor": "#208AEF",
          "image": "./assets/images/splash-icon.png",
          "imageWidth": 76
        }
      ],
      "@rnmapbox/maps",
      [
        "expo-location",
        {
          "locationWhenInUsePermission": "SafeRoute uses your location to center the map on you and find the safest route from where you are."
        }
      ]
    ],
    "experiments": {
      "typedRoutes": true,
      "reactCompiler": true
    },
    "extra": {
      "router": {},
      "eas": {
        "projectId": "ffefe5a9-2ffc-4165-bffc-924c34eb528c"
      }
    }
  }
};
