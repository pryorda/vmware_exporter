#!/bin/ruby
require 'pre-commit-sign'
if ARGV.length >= 1
  puts 'Validating signature'
  commit_message = ARGV[0]
  message_body = commit_message.split("\n").select { |l| l.start_with?('    ') }.join("\n").gsub(/^    /, '')
  pcs = PrecommitSign.from_message(message_body)
  pcs.date = DateTime.strptime(/^Date:\s+(.*)$/.match(commit_message).captures.first, '%a %b %d %T %Y %z').to_time
  puts "Commit Message: #{message_body}"
  if pcs.valid_signature?
    puts 'Perfect'
  else
    puts 'Not valid'
    exit 1
  end
else
  puts "Need a commit message to validate signature from. Try pre-commit install -f && pre-commit install --install-hooks -t commit-msg -f before commiting your code."
  exit 1
end
