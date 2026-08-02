// Map our env var name onto the one @rnmapbox/maps now expects, so the
// (native) build picks up the download token without the deprecated
// `RNMapboxMapsDownloadToken` plugin option.
process.env.RNMAPBOX_MAPS_DOWNLOAD_TOKEN = process.env.MAPBOX_DOWNLOAD_TOKEN;

const isProductionBuild = process.env.EAS_BUILD_PROFILE === "production";
const requiredPublicConfig = [
  "EXPO_PUBLIC_API_BASE_URL",
  "EXPO_PUBLIC_MAPBOX_TOKEN",
  "EXPO_PUBLIC_SUPABASE_URL",
  "EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
];
if (isProductionBuild) {
  const missing = requiredPublicConfig.filter((name) => !process.env[name]);
  if (missing.length > 0 || !process.env.MAPBOX_DOWNLOAD_TOKEN) {
    if (!process.env.MAPBOX_DOWNLOAD_TOKEN) missing.push("MAPBOX_DOWNLOAD_TOKEN");
    throw new Error(`Missing production build configuration: ${missing.join(", ")}`);
  }

  const invalid = [];
  const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;
  const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
  try {
    const parsedApiUrl = new URL(apiBaseUrl);
    if (
      parsedApiUrl.protocol !== "https:" ||
      parsedApiUrl.hostname.includes("your-backend") ||
      parsedApiUrl.hostname.endsWith(".example.com")
    ) {
      invalid.push("EXPO_PUBLIC_API_BASE_URL");
    }
  } catch {
    invalid.push("EXPO_PUBLIC_API_BASE_URL");
  }
  try {
    const parsedSupabaseUrl = new URL(supabaseUrl);
    if (
      parsedSupabaseUrl.protocol !== "https:" ||
      parsedSupabaseUrl.pathname !== "/" ||
      !parsedSupabaseUrl.hostname.endsWith(".supabase.co")
    ) {
      invalid.push("EXPO_PUBLIC_SUPABASE_URL");
    }
  } catch {
    invalid.push("EXPO_PUBLIC_SUPABASE_URL");
  }
  if (!process.env.EXPO_PUBLIC_MAPBOX_TOKEN.startsWith("pk.") || process.env.EXPO_PUBLIC_MAPBOX_TOKEN.length < 50) {
    invalid.push("EXPO_PUBLIC_MAPBOX_TOKEN");
  }
  if (!process.env.MAPBOX_DOWNLOAD_TOKEN.startsWith("sk.") || process.env.MAPBOX_DOWNLOAD_TOKEN.length < 50) {
    invalid.push("MAPBOX_DOWNLOAD_TOKEN");
  }
  if (process.env.EXPO_PUBLIC_USE_MOCK_DATA !== "false") {
    invalid.push("EXPO_PUBLIC_USE_MOCK_DATA");
  }
  if (invalid.length > 0) {
    throw new Error(
      `Invalid production build configuration: ${[...new Set(invalid)].join(", ")}`,
    );
  }
}

export default {
  "expo": {
    "name": "SafeRoute",
    "slug": "saferoute",
    "version": "1.0.0",
    "orientation": "portrait",
    "icon": "./assets/images/icon-v2.png",
    "scheme": "saferoute",
    "userInterfaceStyle": "automatic",
    "ios": {
      "icon": "./assets/expo.icon",
      "bundleIdentifier": "com.saferoute.mobileapp",
      "infoPlist": {
        "ITSAppUsesNonExemptEncryption": false,
        "NSLocationWhenInUseUsageDescription": "SafeRoute konumunuzu haritada göstermek ve seçtiğiniz hedefe yürüyüş seçenekleri üretmek için kullanır."
      },
      "config": {
        "usesNonExemptEncryption": false
      }
    },
    "android": {
      "adaptiveIcon": {
        "backgroundColor": "#E6F4FE",
        "foregroundImage": "./assets/images/android-icon-foreground-v2.png",
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
      "expo-secure-store",
      [
        "expo-splash-screen",
        {
          "backgroundColor": "#F7F9FF",
          "image": "./assets/images/splash-icon-v2.png",
          "imageWidth": 112
        }
      ],
      "@rnmapbox/maps",
      [
        "expo-location",
        {
          "locationWhenInUsePermission": "SafeRoute konumunuzu haritada göstermek ve seçtiğiniz hedefe yürüyüş seçenekleri üretmek için kullanır."
        }
      ],
      [
        "expo-notifications",
        {
          "icon": "./assets/images/icon-v2.png",
          "color": "#3A5F81",
          "defaultChannel": "emergency"
        }
      ]
    ],
    "notification": {
      "icon": "./assets/images/icon-v2.png",
      "color": "#3A5F81",
      "androidMode": "default",
      "androidCollapsedTitle": "SafeRoute acil uyarı"
    },
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
