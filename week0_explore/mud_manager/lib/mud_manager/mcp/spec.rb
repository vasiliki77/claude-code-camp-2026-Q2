require "json"
require_relative "../version"
require_relative "tool_spec"

module MudManager
  module Mcp
    # Generates `primitives.json` — plan §4.4's language-neutral source of truth.
    #
    # Direction matters and was settled by open-Q #4: **Ruby is canonical**, so
    # this file is a *renderer*, not a parser. `primitives.json` is generated
    # from `ToolSpec` (which in turn reads `MudManager::Primitives` enums live),
    # never hand-edited. Any track that wants locally-typed builders generates
    # them from the emitted file, so the cohort cannot drift.
    #
    # This artifact is shared by five language tracks. A diff here is a change
    # to a contract other people are generating code from — check it before
    # shipping, not after.
    module Spec
      SCHEMA_NOTE = "Generated from MudManager::Mcp::ToolSpec, which reads " \
                    "MudManager::Primitives enum constants at call time. " \
                    "Ruby is canonical; do not hand-edit this file.".freeze

      module_function

      def to_h
        {
          "$schema_note" => SCHEMA_NOTE,
          "version" => MudManager::VERSION,
          "generator" => "mud-manager",
          "tools" => ToolSpec.tools.map { |t| render(t) }
        }
      end

      def render(tool)
        {
          "name" => tool["name"],
          "primitive" => tool["primitive"],
          "group" => tool["group"],
          "description" => tool["description"],
          "args" => tool["args"]
        }
      end

      # Pretty-printed with a trailing newline: this file is read by humans and
      # diffed in review, and a one-line JSON blob defeats both.
      def to_json_text
        JSON.pretty_generate(to_h) + "\n"
      end

      def write(path)
        File.write(path, to_json_text)
        path
      end

      def default_path
        File.expand_path("../../../primitives.json", __dir__)
      end
    end
  end
end
