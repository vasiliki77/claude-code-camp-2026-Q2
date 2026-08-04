require "socket"

module MudManager
  # A minimal stand-in for a CircleMUD server.
  #
  # This is a **domain** test double, not part of the MCP layer — it is a fake
  # *MUD*, speaking telnet and running the login dance, and it would still make
  # sense if the daemon had never been written. That is why it lives at
  # `MudManager::FakeMud` rather than under `MudManager::Mcp`.
  #
  # It exists because every interesting test of the daemon needs a socket that
  # completes a login and terminates responses with CircleMUD's `"> "` prompt
  # sentinel. Requiring a real MUD to be running turns the whole suite into an
  # integration test that a bootcamper cannot run on a train.
  #
  #   mud = MudManager::FakeMud.new(password: "secret").start
  #   session = MudManager::Session.new(host: "127.0.0.1", port: mud.port)
  #   session.open
  #   session.login("Gandalf", "secret")
  #   mud.stop
  class FakeMud
    PROMPT = "<100hp 50m 30v> ".freeze

    attr_reader :port, :password, :received

    # responses:       exact-match command => reply text (prompt appended for you)
    # already_in_use:  simulate a character still in-world from a prior
    #                  connection, so login takes the take-over path
    def initialize(port: 0, password: "secret", responses: {}, already_in_use: false)
      @requested_port = port
      @password = password
      @responses = responses
      @already_in_use = already_in_use
      @received = []
      @logins = 0
      @mutex = Mutex.new
      @clients = []
      @server = nil
      @thread = nil
    end

    # How many times a client has completed the login dance. The daemon's whole
    # reason to exist is that this stays at 1 across many commands (plan §2):
    # a per-command CLI would re-login on every call.
    def logins
      @mutex.synchronize { @logins }
    end

    def start
      # Port 0 asks the OS for a free one, so parallel test runs cannot collide
      # on a hardcoded port.
      @server = TCPServer.new("127.0.0.1", @requested_port)
      @port = @server.addr[1]

      @thread = Thread.new do
        loop do
          client = @server.accept
          @mutex.synchronize { @clients << client }
          Thread.new { serve(client) }
        end
      rescue IOError, Errno::EBADF
        # server closed — normal shutdown
      end
      @thread.report_on_exception = false

      self
    end

    def stop
      @thread&.kill
      @mutex.synchronize do
        @clients.each { |c| c.close rescue nil }
        @clients.clear
      end
      @server&.close rescue nil
      @server = nil
    end

    # Push unsolicited output to every connected client — a combat round, a
    # player shouting. This is what makes `poll` testable: async chatter that
    # arrives when the agent did not ask for anything.
    def broadcast(text)
      @mutex.synchronize do
        @clients.each do |c|
          begin
            c.write(text)
          rescue StandardError
            # client gone; stop is responsible for reaping
          end
        end
      end
    end

    def commands
      @mutex.synchronize { @received.dup }
    end

    private

    def serve(client)
      client.write("\r\nBy what name do you wish to be known? ")
      name = client.gets
      return if name.nil?

      client.write("Password: ")
      given = client.gets
      return if given.nil?

      if given.to_s.strip != @password
        client.write("Wrong password.\r\n")
        client.close
        return
      end

      @mutex.synchronize { @logins += 1 }

      # A character that is still in-world from a previous connection does not
      # get the menu. tbaMUD drops you straight back into your body — the
      # linkdead take-over path, which is routine after a daemon exits.
      if @already_in_use
        client.write("\r\nYou take over your own body, already in use!\r\n#{PROMPT}")
      else
        # Fresh-login branch of Session#login: a "Welcome" line, then the main
        # menu, which the session answers with a blank line and then "1".
        client.write("\r\nWelcome to the Fake Lands, #{name.to_s.strip}!\r\n")
        client.write("0) Exit.\r\n1) Enter the game.\r\n\r\nMake your choice: ")
      end

      loop do
        line = client.gets
        break if line.nil?

        command = line.to_s.strip
        @mutex.synchronize { @received << command }

        client.write(reply_for(command))
      end
    rescue Errno::ECONNRESET, Errno::EPIPE, IOError
      # client vanished — nothing to do
    ensure
      client.close rescue nil
      @mutex.synchronize { @clients.delete(client) }
    end

    def reply_for(command)
      return "" if command.empty? # the blank line answering the menu

      body =
        if @responses.key?(command)
          @responses[command]
        elsif command == "1"
          "You wake up in the Temple of Midgaard.\r\n" \
          "A fountain bubbles quietly here.\r\n"
        else
          # Echoing the command is enough for a test to assert the right line
          # reached the MUD, which is the thing the daemon is responsible for.
          "You #{command}.\r\n"
        end

      "#{body}#{PROMPT}"
    end
  end
end
