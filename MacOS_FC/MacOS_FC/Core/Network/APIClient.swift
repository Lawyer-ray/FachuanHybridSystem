//
//  APIClient.swift
//  MacOS_FC
//
//  HTTP API 客户端
//

import Foundation
import os.log

final class APIClient {
    static let shared = APIClient()
    
    private let session: URLSession
    private let logger = Logger(subsystem: "com.fachuan.macos", category: "network")
    private let decoder: JSONDecoder
    
    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        self.session = URLSession(configuration: config)
        
        self.decoder = JSONDecoder()
        self.decoder.keyDecodingStrategy = .convertFromSnakeCase
    }
    
    // MARK: - Public Methods
    
    func get<T: Decodable>(_ endpoint: String) async throws -> T {
        let request = try buildRequest(endpoint, method: "GET")
        return try await execute(request, allowRefresh: true)
    }
    
    func post<T: Decodable, B: Encodable>(_ endpoint: String, body: B) async throws -> T {
        var request = try buildRequest(endpoint, method: "POST")
        request.httpBody = try JSONEncoder().encode(body)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return try await execute(request, allowRefresh: true)
    }
    
    func refreshToken(_ refreshToken: String) async throws -> String {
        struct RefreshRequest: Encodable {
            let refresh: String
        }
        
        struct RefreshResponse: Decodable {
            let access: String
        }
        
        var request = try buildRequest("/token/refresh", method: "POST")
        request.httpBody = try JSONEncoder().encode(RefreshRequest(refresh: refreshToken))
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let response: RefreshResponse = try await execute(request, allowRefresh: false)
        
        return response.access
    }
    
    // MARK: - 合同 API
    
    func getContracts() async throws -> [Contract] {
        struct ContractsResponse: Decodable {
            let items: [Contract]
        }
        let response: ContractsResponse = try await get("/contracts/")
        return response.items
    }
    
    func getContract(id: Int) async throws -> Contract {
        try await get("/contracts/\(id)")
    }
    
    // MARK: - 案件 API
    
    func getCases() async throws -> [Case] {
        struct CasesResponse: Decodable {
            let items: [Case]
        }
        let response: CasesResponse = try await get("/cases/")
        return response.items
    }
    
    func getCase(id: Int) async throws -> Case {
        try await get("/cases/\(id)")
    }
    
    // MARK: - Private Methods
    
    private func buildRequest(_ endpoint: String, method: String) throws -> URLRequest {
        guard let url = URL(string: AppConfig.apiBaseURL + endpoint) else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        
        // 添加认证头
        if let token = TokenManager.shared.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        return request
    }
    
    private func execute<T: Decodable>(_ request: URLRequest, allowRefresh: Bool) async throws -> T {
        logger.info("API 请求: \(request.httpMethod ?? "GET") \(request.url?.absoluteString ?? "")")
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        logger.info("API 响应: \(httpResponse.statusCode)")
        
        switch httpResponse.statusCode {
        case 200...299:
            return try decoder.decode(T.self, from: data)
        case 401:
            // Token 过期，尝试刷新
            guard allowRefresh else {
                throw APIError.unauthorized
            }
            
            if let newToken = try? await TokenManager.shared.refreshAccessToken() {
                var newRequest = request
                newRequest.setValue("Bearer \(newToken)", forHTTPHeaderField: "Authorization")
                let (retryData, retryResponse) = try await session.data(for: newRequest)
                
                guard let retryHttpResponse = retryResponse as? HTTPURLResponse,
                      (200...299).contains(retryHttpResponse.statusCode) else {
                    throw APIError.unauthorized
                }
                
                return try decoder.decode(T.self, from: retryData)
            }
            throw APIError.unauthorized
        case 403:
            throw APIError.forbidden
        case 404:
            throw APIError.notFound
        default:
            throw APIError.serverError(httpResponse.statusCode)
        }
    }
}

// MARK: - API 错误

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case unauthorized
    case forbidden
    case notFound
    case serverError(Int)
    case decodingError(Error)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL: return "无效的 URL"
        case .invalidResponse: return "无效的响应"
        case .unauthorized: return "未授权，请重新登录"
        case .forbidden: return "无权访问"
        case .notFound: return "资源不存在"
        case .serverError(let code): return "服务器错误: \(code)"
        case .decodingError(let error): return "数据解析错误: \(error.localizedDescription)"
        }
    }
}
