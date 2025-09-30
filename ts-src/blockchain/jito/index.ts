// Use type declarations instead of direct imports
// This helps TypeScript work without requiring the exact module resolution

// Define types for what we need to export
type BlockEngineClient = any;
type Bundle = any;
type BundleResult = any;
type NextScheduledLeaderClient = any;

// Export the components as types
export { 
  BlockEngineClient as jito, 
  Bundle, 
  BundleResult, 
  NextScheduledLeaderClient 
};