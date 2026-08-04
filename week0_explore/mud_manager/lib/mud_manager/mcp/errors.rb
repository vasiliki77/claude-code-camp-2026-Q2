module MudManager
  module Mcp
    # Structured errors.
    #
    # Plan open-Q #3: foreign-language clients must be able to *branch* on a
    # failure, not parse prose. Every error that crosses the daemon boundary
    # therefore carries a stable machine-readable `code` alongside its human
    # message, and serialises to the same shape in both protocols:
    #
    #   {"code": "TIMEOUT", "message": "...", "data": {...}}
    #
    # The codes are the daemon's public contract. Adding one is cheap; renaming
    # one breaks every client in the cohort.
    class Error < StandardError
      attr_reader :code, :data

      def initialize(message, code: "INTERNAL", data: nil)
        super(message)
        @code = code
        @data = data
      end

      def to_h
        h = { "code" => code, "message" => message }
        h["data"] = data if data
        h
      end

      # Map a MudManager::Session exception onto a daemon error. Session is the
      # domain layer and knows nothing about protocols, so the translation lives
      # here rather than there.
      def self.from_session(err)
        case err
        when MudManager::Session::Timeout
          new(err.message, code: "TIMEOUT")
        when MudManager::Session::LoginError
          new(err.message, code: "LOGIN_FAILED")
        when MudManager::Session::ConnectionError
          new(err.message, code: "CONNECTION_FAILED")
        when MudManager::Session::Error
          new(err.message, code: "SESSION_ERROR")
        else
          new("#{err.class}: #{err.message}", code: "INTERNAL")
        end
      end
    end

    # The caller named a tool the daemon does not serve.
    class UnknownToolError < Error
      def initialize(name)
        super("No tool named #{name.inspect}", code: "UNKNOWN_TOOL", data: { "tool" => name.to_s })
      end
    end

    # Arguments failed validation — either the daemon's own required-argument
    # check or Primitives' enum check. This is the error an LLM is most likely
    # to cause, so the message deliberately repeats the allowed values.
    class ValidationError < Error
      def initialize(message, tool: nil)
        super(message, code: "INVALID_ARGUMENTS", data: tool ? { "tool" => tool.to_s } : nil)
      end
    end

    # Malformed frame on the wire: unparseable JSON, missing `op`, bad JSON-RPC.
    class ProtocolError < Error
      def initialize(message)
        super(message, code: "PROTOCOL_ERROR")
      end
    end
  end
end
