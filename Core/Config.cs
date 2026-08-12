using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;

namespace AgentBridge.Core
{
    public static class Config
    {
        public const int CurrentSchemaVersion = 2;
        private static readonly object SyncRoot = new object();
        private static Dictionary<string, string> _settings = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static string _configPath;

        public static void Load()
        {
            lock (SyncRoot)
            {
                string dllDir = Path.GetDirectoryName(typeof(Config).Assembly.Location);
                _configPath = Path.Combine(dllDir ?? AppDomain.CurrentDomain.BaseDirectory, "agentbridge.config.json");

                if (!File.Exists(_configPath))
                {
                    _settings = CreateDefaultSettings();
                    SaveLocked();
                    return;
                }

                try
                {
                    string json = File.ReadAllText(_configPath);
                    _settings = JsonConvert.DeserializeObject<Dictionary<string, string>>(json)
                        ?? CreateDefaultSettings();
                    if (MigrateLocked())
                    {
                        SaveLocked();
                    }
                }
                catch (Exception ex)
                {
                    _settings = CreateDefaultSettings();
                    Logger.Error("Failed to load config: " + ex.Message);
                }
            }
        }

        public static string Get(string key, string defaultValue)
        {
            string envValue = Environment.GetEnvironmentVariable("CADCOPILOT_" + key);
            if (!string.IsNullOrWhiteSpace(envValue))
            {
                return envValue;
            }

            lock (SyncRoot)
            {
                string value;
                return _settings.TryGetValue(key, out value) ? value : defaultValue;
            }
        }

        public static void Set(string key, string value)
        {
            lock (SyncRoot)
            {
                _settings[key] = value ?? string.Empty;
                SaveLocked();
            }
        }

        public static void SetMany(params KeyValuePair<string, string>[] entries)
        {
            if (entries == null || entries.Length == 0)
            {
                return;
            }

            lock (SyncRoot)
            {
                for (int i = 0; i < entries.Length; i++)
                {
                    _settings[entries[i].Key] = entries[i].Value ?? string.Empty;
                }

                SaveLocked();
            }
        }

        public static bool IsSchemaVersionSupported()
        {
            int version;
            return int.TryParse(Get("CONFIG_SCHEMA_VERSION", "1"), out version)
                && version <= CurrentSchemaVersion;
        }

        private static bool MigrateLocked()
        {
            int version;
            if (!int.TryParse(
                _settings.ContainsKey("CONFIG_SCHEMA_VERSION") ? _settings["CONFIG_SCHEMA_VERSION"] : "1",
                out version))
            {
                version = 1;
            }

            if (version > CurrentSchemaVersion)
            {
                Logger.Error("Config schema version " + version + " is newer than supported version " + CurrentSchemaVersion + ".");
                return false;
            }

            bool changed = false;
            Dictionary<string, string> defaults = CreateDefaultSettings();
            foreach (KeyValuePair<string, string> entry in defaults)
            {
                if (!_settings.ContainsKey(entry.Key))
                {
                    _settings[entry.Key] = entry.Value;
                    changed = true;
                }
            }

            if (version < CurrentSchemaVersion)
            {
                _settings["CONFIG_SCHEMA_VERSION"] = CurrentSchemaVersion.ToString();
                changed = true;
                Logger.Info("Migrated plugin config schema from version " + version + " to " + CurrentSchemaVersion + ".");
            }

            return changed;
        }

        private static void SaveLocked()
        {
            try
            {
                if (string.IsNullOrWhiteSpace(_configPath))
                {
                    string dllDir = Path.GetDirectoryName(typeof(Config).Assembly.Location);
                    _configPath = Path.Combine(dllDir ?? AppDomain.CurrentDomain.BaseDirectory, "agentbridge.config.json");
                }

                string json = JsonConvert.SerializeObject(_settings, Formatting.Indented);
                File.WriteAllText(_configPath, json);
            }
            catch (Exception ex)
            {
                Logger.Error("Failed to save config: " + ex.Message);
            }
        }

        private static Dictionary<string, string> CreateDefaultSettings()
        {
            return new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                ["CADCOPILOT_CONNECTION_MODE"] = "standard",
                ["LLM_PROVIDER"] = "cadcopilot",
                ["CLAUDE_API_KEY"] = "",
                ["CLAUDE_MODEL"] = "claude-sonnet-4-20250514",
                ["OPENAI_API_KEY"] = "",
                ["OPENAI_API_BASE_URL"] = "https://api.minimaxi.com/v1",
                ["OPENAI_MODEL"] = "MiniMax-M2.7",
                ["DIRECT_MODEL_PROFILES"] = "",
                ["ACTIVE_DIRECT_MODEL"] = "MiniMax-M2.7",
                ["SERVICE_MODEL_PROFILES"] = "",
                ["ACTIVE_SERVICE_MODEL"] = "MiniMax-M2.7",
                ["CADCOPILOT_MODEL"] = "MiniMax-M2.7",
                ["CADCOPILOT_API_BASE_URL"] = "http://127.0.0.1:8000",
                ["CADCOPILOT_CLIENT_ID"] = "cad-plugin",
                ["LOCAL_BRIDGE_ENABLED"] = "true",
                ["LOCAL_BRIDGE_HOST"] = "127.0.0.1",
                ["LOCAL_BRIDGE_PORT"] = "8765",
                ["LOCAL_BRIDGE_TOKEN"] = "",
                ["LOCAL_BRIDGE_REQUIRE_TOKEN"] = "false",
                ["CONFIG_SCHEMA_VERSION"] = "2",
                ["ENVIRONMENT"] = "development",
                ["LOG_LEVEL"] = "INFO"
            };
        }
    }
}
