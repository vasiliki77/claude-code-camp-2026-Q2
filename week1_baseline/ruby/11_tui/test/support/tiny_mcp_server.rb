#!/usr/bin/env ruby
# frozen_string_literal: true
#
# A throwaway MCP server with nothing to do with MUDs.
#
# It exists so that "Boukensha::Tools::Mcp is generic" is proven by
# demonstration rather than asserted in a comment. If MUD assumptions creep back
# into the host layer, the tests using this server fail loudly.
#
# Two tools, no state, no dependencies.
require "json"

TOOLS = [
  { "name" => "add",
    "description" => "Add two numbers together.",
    "inputSchema" => {
      "type" => "object",
      "properties" => {
        "a" => { "type" => "number", "description" => "first addend" },
        "b" => { "type" => "number", "description" => "second addend" }
      },
      "required" => %w[a b]
    } },
  { "name" => "shout",
    "description" => "Uppercase some text.",
    "inputSchema" => {
      "type" => "object",
      "properties" => { "text" => { "type" => "string", "description" => "the text" } },
      "required" => %w[text]
    } }
].freeze

$stdout.sync = true

$stdin.each_line do |line|
  line = line.strip
  next if line.empty?

  message = JSON.parse(line)
  next if message["id"].nil? # notification — act on nothing, answer nothing

  result =
    case message["method"]
    when "initialize"
      { "protocolVersion" => "2024-11-05",
        "capabilities" => { "tools" => { "listChanged" => false } },
        "serverInfo" => { "name" => "tiny-calculator", "version" => "1.0.0" } }
    when "tools/list"
      { "tools" => TOOLS }
    when "tools/call"
      args = message.dig("params", "arguments") || {}
      text =
        case message.dig("params", "name")
        when "add"   then (args["a"].to_f + args["b"].to_f).to_s
        when "shout" then args["text"].to_s.upcase
        else "no such tool"
        end
      { "content" => [{ "type" => "text", "text" => text }], "isError" => false }
    end

  puts JSON.generate({ "jsonrpc" => "2.0", "id" => message["id"], "result" => result })
end
