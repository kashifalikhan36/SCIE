const fs = require("fs");
const path = require("path");

const outDir = path.join(__dirname, "out");

function extractInlineScripts(filePath) {
  const content = fs.readFileSync(filePath, "utf8");
  const scriptTagRegex = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  const dir = path.dirname(filePath);
  const baseName = path.basename(filePath, ".html");
  let index = 0;
  
  let newContent = content.replace(scriptTagRegex, (match, attrs, body) => {
    // Check if it's already an external script (has src)
    if (attrs.includes("src=")) {
      return match;
    }
    
    const trimmedBody = body.trim();
    if (!trimmedBody) {
      return ""; // remove empty script tags
    }
    
    // Generate inline script file name and path
    const inlineFileName = `${baseName}-inline-${index}.js`;
    const inlineFilePath = path.join(dir, inlineFileName);
    
    // Save inline JS to its own file
    fs.writeFileSync(inlineFilePath, trimmedBody, "utf8");
    console.log(`Extracted inline script from ${path.relative(outDir, filePath)} to: ${inlineFileName}`);
    
    index++;
    // Return script tag referencing the new script file
    return `<script ${attrs} src="${inlineFileName}"></script>`;
  });
  
  if (newContent !== content) {
    fs.writeFileSync(filePath, newContent, "utf8");
  }
}

function fixPaths(dir) {
  if (!fs.existsSync(dir)) return;
  const files = fs.readdirSync(dir);
  
  for (const file of files) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    
    if (stat.isDirectory()) {
      fixPaths(filePath);
    } else if (file.endsWith(".html")) {
      // 1. Replace underscore paths first
      let content = fs.readFileSync(filePath, "utf8");
      let updated = false;
      if (content.includes("_next/")) {
        content = content.replace(/_next\//g, "next/");
        updated = true;
      }
      if (content.includes("_not-found")) {
        content = content.replace(/_not-found/g, "not-found");
        updated = true;
      }
      if (updated) {
        fs.writeFileSync(filePath, content, "utf8");
        console.log(`Updated paths in: ${path.relative(outDir, filePath)}`);
      }
      
      // 2. Extract inline scripts for CSP compliance
      extractInlineScripts(filePath);
    } else if (
      file.endsWith(".js") || 
      file.endsWith(".css") || 
      file.endsWith(".txt") ||
      file.endsWith(".json")
    ) {
      let content = fs.readFileSync(filePath, "utf8");
      let updated = false;
      if (content.includes("_next/")) {
        content = content.replace(/_next\//g, "next/");
        updated = true;
      }
      if (content.includes("_not-found")) {
        content = content.replace(/_not-found/g, "not-found");
        updated = true;
      }
      if (updated) {
        fs.writeFileSync(filePath, content, "utf8");
        console.log(`Updated paths in: ${path.relative(outDir, filePath)}`);
      }
    }
  }
}

function run() {
  console.log("Fixing Next.js static export for Chrome Extension...");

  if (!fs.existsSync(outDir)) {
    console.error(`Error: Directory ${outDir} does not exist. Run next build first.`);
    process.exit(1);
  }

  // 1. Rename _next directory to next
  const oldNext = path.join(outDir, "_next");
  const newNext = path.join(outDir, "next");
  if (fs.existsSync(oldNext)) {
    if (fs.existsSync(newNext)) {
      fs.rmSync(newNext, { recursive: true, force: true });
    }
    fs.renameSync(oldNext, newNext);
    console.log("Renamed _next/ directory to next/");
  }

  // 2. Rename _not-found directory to not-found
  const oldNotFound = path.join(outDir, "_not-found");
  const newNotFound = path.join(outDir, "not-found");
  if (fs.existsSync(oldNotFound)) {
    if (fs.existsSync(newNotFound)) {
      fs.rmSync(newNotFound, { recursive: true, force: true });
    }
    fs.renameSync(oldNotFound, newNotFound);
    console.log("Renamed _not-found/ directory to not-found/");
  }

  // 3. Rename _not-found.html and _not-found.txt if they exist
  const filesToRename = ["_not-found.html", "_not-found.txt"];
  filesToRename.forEach(f => {
    const oldFile = path.join(outDir, f);
    const newFile = path.join(outDir, f.replace("_", ""));
    if (fs.existsSync(oldFile)) {
      fs.renameSync(oldFile, newFile);
      console.log(`Renamed ${f} to ${f.replace("_", "")}`);
    }
  });

  // 3.5 Delete all remaining files or folders starting with "_" in the output directory
  const outFiles = fs.readdirSync(outDir);
  outFiles.forEach(f => {
    if (f.startsWith("_")) {
      const fullPath = path.join(outDir, f);
      const stat = fs.statSync(fullPath);
      if (stat.isDirectory()) {
        fs.rmSync(fullPath, { recursive: true, force: true });
        console.log(`Deleted directory starting with underscore: ${f}`);
      } else {
        fs.rmSync(fullPath, { force: true });
        console.log(`Deleted file starting with underscore: ${f}`);
      }
    }
  });

  // 4. Update references recursively in all build files
  fixPaths(outDir);
  console.log("Next.js static export fixed successfully!");
}

run();
