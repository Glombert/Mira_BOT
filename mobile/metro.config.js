const path = require('path');
const { getDefaultConfig, mergeConfig } = require('@react-native/metro-config');

const defaultConfig = getDefaultConfig(__dirname);
const { assetExts, sourceExts } = defaultConfig.resolver;

// Общий пакет дизайн-токенов/контракта живёт в монорепо: clients/packages/shared/src.
// watchFolders + extraNodeModules позволяют импортить '@mira/shared/...' из мобайла.
const sharedSrc = path.resolve(__dirname, '../clients/packages/shared/src');

/** @type {import('@react-native/metro-config').MetroConfig} */
const config = {
  transformer: {
    babelTransformerPath: require.resolve('react-native-svg-transformer'),
  },
  resolver: {
    assetExts: assetExts.filter((ext) => ext !== 'svg'),
    sourceExts: [...sourceExts, 'svg'],
    extraNodeModules: {
      '@mira/shared': sharedSrc,
    },
  },
  watchFolders: [sharedSrc],
};

module.exports = mergeConfig(defaultConfig, config);
