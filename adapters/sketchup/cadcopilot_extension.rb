# AgentBridge Host — SketchUp extension loader (Extension Manager registration).
#
# Build the .rbz with scripts/pack-sketchup-extension.ps1, then install via
# SketchUp: Extensions (Extension Manager) -> Install Extension.

require 'sketchup.rb'
require 'extensions.rb'

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
