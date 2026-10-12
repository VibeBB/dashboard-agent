# mruby/c UX leg for the smart-kettle dashboard.
# Runs inside the Emscripten WASM VM under the `wasm.mrubyc` gate.
fill = 0
3.times do
  fill += 25
  puts "kettle fill #{fill}%"
end
puts "kettle ready"

# Device-API stub calls: logged to the transcript by the generated
# dash_api_stub bindings so `expect` entries can assert them.
LED.set(part: :led1, state: true)
LED.toggle(:led1)
