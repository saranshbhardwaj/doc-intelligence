// src/components/landing/Hero.jsx
import { ArrowRight, FileText, Zap, TrendingUp } from "lucide-react";

export default function Hero({ onGetStarted, onTryDemo }) {
  return (
    <div className="relative overflow-hidden bg-gradient-to-br from-blue-50 via-white to-purple-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-purple-300 rounded-full mix-blend-multiply filter blur-xl opacity-20 animate-blob"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-blue-300 rounded-full mix-blend-multiply filter blur-xl opacity-20 animate-blob animation-delay-2000"></div>
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-80 h-80 bg-pink-300 rounded-full mix-blend-multiply filter blur-xl opacity-20 animate-blob animation-delay-4000"></div>
      </div>

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 sm:py-32">
        <div className="text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-sm font-medium mb-8">
            <Zap className="w-4 h-4" />
            AI-Powered CIM Analysis
          </div>

          {/* Main heading */}
          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-extrabold text-gray-900 dark:text-white mb-6 leading-tight">
            Extract Deal Data from
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              {" "}
              CIMs in Minutes
            </span>
          </h1>

          {/* Subheading */}
          <p className="text-xl sm:text-2xl text-gray-600 dark:text-gray-300 mb-10 max-w-3xl mx-auto leading-relaxed">
            Stop spending hours extracting financials from documents. Our AI
            reads CIMs and delivers structured data in Excel ready for your
            model.
          </p>

          {/* Stats */}
          <div className="flex flex-wrap justify-center gap-8 mb-12">
            <div className="text-center">
              <div className="text-4xl font-bold text-blue-600 dark:text-blue-400">
                4 min
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Average processing time
              </div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-bold text-purple-600 dark:text-purple-400">
                95%+
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Extraction accuracy
              </div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-bold text-pink-600 dark:text-pink-400">
                12+
              </div>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Data categories extracted
              </div>
            </div>
          </div>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <button
              onClick={onGetStarted}
              className="group px-8 py-4 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white font-semibold rounded-xl shadow-lg hover:shadow-xl transform hover:scale-105 transition-all duration-200 flex items-center gap-2"
            >
              Get Started Free
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </button>
            <button
              onClick={onTryDemo}
              className="px-8 py-4 bg-white dark:bg-gray-800 border-2 border-gray-300 dark:border-gray-600 hover:border-blue-500 dark:hover:border-blue-500 text-gray-900 dark:text-white font-semibold rounded-xl shadow hover:shadow-lg transform hover:scale-105 transition-all duration-200 flex items-center gap-2"
            >
              <FileText className="w-5 h-5" />
              View Sample Output
            </button>
          </div>

          {/* Trust badge */}
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-8">
            No credit card required • up to 100 pages • Cancel anytime
          </p>
        </div>

        {/* Feature highlights */}
        <div className="mt-20 grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          <div className="flex items-start gap-4 p-6 rounded-xl bg-white/50 dark:bg-gray-800/50 backdrop-blur border border-gray-200 dark:border-gray-700">
            <div className="flex-shrink-0 w-12 h-12 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
              <Zap className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                Lightning Fast
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Process 30+ page CIMs in under 5 minutes
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4 p-6 rounded-xl bg-white/50 dark:bg-gray-800/50 backdrop-blur border border-gray-200 dark:border-gray-700">
            <div className="flex-shrink-0 w-12 h-12 bg-purple-100 dark:bg-purple-900/30 rounded-lg flex items-center justify-center">
              <TrendingUp className="w-6 h-6 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                Excel Export
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Structured data ready for your financial models
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4 p-6 rounded-xl bg-white/50 dark:bg-gray-800/50 backdrop-blur border border-gray-200 dark:border-gray-700">
            <div className="flex-shrink-0 w-12 h-12 bg-pink-100 dark:bg-pink-900/30 rounded-lg flex items-center justify-center">
              <FileText className="w-6 h-6 text-pink-600 dark:text-pink-400" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                Red Flag Detection
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Automatic risk analysis on every deal
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
