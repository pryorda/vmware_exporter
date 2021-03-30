#!/bin/ruby
require 'pre-commit-sign'
if ARGV.length >= 1
  puts "Validating signature"
  pcs = PrecommitSign.from_message(${{ github.event.head_commit.message }})
  if pcs.valid_signature?:
    puts "Perfect"
  else
    puts "Not valid"
    exit 1
  end
else
  puts "No Commit message can't validate signature"
  exit 1
end
