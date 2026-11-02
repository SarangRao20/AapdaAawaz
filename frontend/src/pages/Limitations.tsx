import { Link } from "react-router-dom";

export function LimitationsPage() {
  return (
    <div className="container mx-auto p-6 max-w-4xl">
      <div className="mb-6">
        <Link to="/live" className="text-blue-600 hover:underline">
          ← Back to Command Center
        </Link>
      </div>

      <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 mb-6">
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-yellow-800">Prototype System</h3>
            <div className="mt-2 text-sm text-yellow-700">
              <p>This is a decision-support prototype. It does not dispatch responders, contact emergency services, or guarantee any outcome. Every action stays with a human dispatcher.</p>
            </div>
          </div>
        </div>
      </div>

      <h1 className="text-3xl font-bold mb-6">Known Limitations</h1>

      <div className="space-y-6">
        {/* Providers Section */}
        <section>
          <h2 className="text-2xl font-semibold mb-3">Speech & Language Models</h2>
          <div className="bg-white rounded-lg border p-4 space-y-3">
            <div>
              <h3 className="font-semibold text-green-700">✅ Gnani Prisma v2.5 (STT)</h3>
              <p className="text-sm text-gray-600 mt-1">Tested and working with live API. Handles Marathi, Hindi, Hinglish, English. Audio preprocessing (spectral noise gate + RMS normalization) available when enabled.</p>
            </div>
            <div>
              <h3 className="font-semibold text-green-700">✅ Gnani Timbre v2.5 (TTS)</h3>
              <p className="text-sm text-gray-600 mt-1">Tested and working with live API. Generates spoken acknowledgements in caller's language.</p>
            </div>
            <div>
              <h3 className="font-semibold text-blue-700">⚙️ Gnani Evon v3.3 (LLM)</h3>
              <p className="text-sm text-gray-600 mt-1">Available as open weights (Apache 2.0) for self-hosted deployment. When deployed, provides natural language summaries and improved extraction accuracy. Currently using rule-based extraction as fallback.</p>
            </div>
          </div>
        </section>

        {/* Extraction Limitations */}
        <section>
          <h2 className="text-2xl font-semibold mb-3">Extraction & Understanding</h2>
          <ul className="bg-white rounded-lg border p-4 space-y-2 text-sm">
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Keyword-based extraction:</strong> Misses synonyms, idioms, spelling variants, and dialects not in the lexicon (e.g., "stranded", "chest pain", "पचास से ज्यादा").</span>
            </li>
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Tense not modeled:</strong> "Everyone was rescued" still triggers as if rescue is needed.</span>
            </li>
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Limited dialect coverage:</strong> Romanized Marathi, Konkani, Ahirani, Varhadi not well supported.</span>
            </li>
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Language detection:</strong> Marker-based, only distinguishes mr/hi/en/mixed.</span>
            </li>
          </ul>
        </section>

        {/* Geolocation */}
        <section>
          <h2 className="text-2xl font-semibold mb-3">Location & Mapping</h2>
          <ul className="bg-white rounded-lg border p-4 space-y-2 text-sm">
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Limited gazetteer:</strong> Only 10 reference places near Pune; real deployment needs a full geographic database.</span>
            </li>
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Generic landmarks:</strong> "The big bridge" produces candidate lists, not exact locations.</span>
            </li>
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Village centroids:</strong> Multiple incidents in one village share one point; map clusters them.</span>
            </li>
          </ul>
        </section>

        {/* Duplicate Detection & Priority */}
        <section>
          <h2 className="text-2xl font-semibold mb-3">Matching & Prioritization</h2>
          <ul className="bg-white rounded-lg border p-4 space-y-2 text-sm">
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Hand-tuned weights:</strong> Thresholds set on limited data, not validated operationally or clinically.</span>
            </li>
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>No resource awareness:</strong> Priority ignores fire-brigade requests, time since report, or resource availability.</span>
            </li>
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Holdout accuracy:</strong> 50% priority accuracy on 12 holdout samples (rule-based); 5 cases under-triaged, 1 over-triaged.</span>
            </li>
          </ul>
        </section>

        {/* System & Deployment */}
        <section>
          <h2 className="text-2xl font-semibold mb-3">System & Deployment</h2>
          <ul className="bg-white rounded-lg border p-4 space-y-2 text-sm">
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>One shared login:</strong> One admin account with no roles. Reviewer name is free text.</span>
            </li>
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Single-process worker:</strong> SQLite not suitable for concurrent multi-user load.</span>
            </li>
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Polling updates:</strong> 2-4 second intervals rather than push.</span>
            </li>
            <li className="flex items-start">
              <span className="text-red-500 mr-2">•</span>
              <span><strong>Synthetic data only:</strong> No real emergency calls tested. ASR errors on noisy, dialectal speech not represented.</span>
            </li>
          </ul>
        </section>

        {/* Production Requirements */}
        <section>
          <h2 className="text-2xl font-semibold mb-3">Production Requirements</h2>
          <div className="bg-blue-50 rounded-lg border border-blue-200 p-4">
            <p className="text-sm text-blue-900 mb-3">Before operational deployment, this system would need:</p>
            <ul className="space-y-1 text-sm text-blue-800">
              <li className="flex items-start">
                <span className="mr-2">→</span>
                <span>User validation with actual emergency dispatchers</span>
              </li>
              <li className="flex items-start">
                <span className="mr-2">→</span>
                <span>Testing on real telephonic audio with background noise</span>
              </li>
              <li className="flex items-start">
                <span className="mr-2">→</span>
                <span>Larger, independently-labeled evaluation datasets</span>
              </li>
              <li className="flex items-start">
                <span className="mr-2">→</span>
                <span>LLM-based extraction (Evon v3.3) or expanded lexicon</span>
              </li>
              <li className="flex items-start">
                <span className="mr-2">→</span>
                <span>PostgreSQL + async workers + WebSocket for real-time updates</span>
              </li>
              <li className="flex items-start">
                <span className="mr-2">→</span>
                <span>Individual accounts, RBAC, audit log signing</span>
              </li>
              <li className="flex items-start">
                <span className="mr-2">→</span>
                <span>Load testing and performance optimization</span>
              </li>
            </ul>
          </div>
        </section>

        {/* Contact */}
        <section className="bg-gray-50 rounded-lg border p-4 text-center">
          <p className="text-sm text-gray-600">
            Built for <strong>The Great Indian AI Internship Challenge</strong> by Gnani AI
          </p>
          <p className="text-xs text-gray-500 mt-2">
            GitHub: <a href="https://github.com/jainamd05/AapdaAawaz" className="text-blue-600 hover:underline">jainamd05/AapdaAawaz</a>
          </p>
        </section>
      </div>
    </div>
  );
}
