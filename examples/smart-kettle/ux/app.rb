# mruby/c UX leg for the smart-kettle dashboard.
# Runs inside the Emscripten WASM VM under the `wasm.mrubyc` gate.
fill = 0
3.times do
  fill += 25
  puts "kettle fill #{fill}%"
end
puts "kettle ready"
