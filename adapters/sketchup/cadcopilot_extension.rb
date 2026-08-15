# AgentBridge Host — SketchUp extension loader (Extension Manager registration).
#
# Build the .rbz with scripts/pack-sketchup-extension.ps1, then install via
# SketchUp: Extensions (Extension Manager) -> Install Extension.

require 'sketchup.rb'
require 'extensions.rb'

# 诊断标记：loader 是否被 SketchUp 加载（每次启动覆盖写时间戳）
begin
  require 'fileutils'
  _marker_dir = File.join(ENV["LOCALAPPDATA"] || ENV["APPDATA"] || Dir.home, "AgentBridge")
  FileUtils.mkdir_p(_marker_dir)
  File.write(File.join(_marker_dir, "sketchup-extension-loader-loaded.txt"), Time.now.utc.iso8601)
rescue StandardError
end

extension_root = File.dirname(__FILE__)
unless defined?(AgentBridgeHost)
  load File.join(extension_root, 'cadcopilot_host.rb')
end

extension = SketchupExtension.new(
  'AgentBridge Host',
  File.join(extension_root, 'cadcopilot_host.rb')
)
extension.description = 'AgentBridge: AI agent bridge to SketchUp (Host Adapter Contract v1)'
extension.version = '1.0.0'
extension.creator = 'AgentBridge'
extension.copyright = 'AgentBridge 2026'

Sketchup.register_extension(extension, true)
