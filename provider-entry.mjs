// Closing the parent application's pipe also stops the private token server.
process.stdin.resume();
process.stdin.on("end", () => process.exit(0));
process.stdin.on("error", () => process.exit(0));
await import("./provider/build/main.js");
