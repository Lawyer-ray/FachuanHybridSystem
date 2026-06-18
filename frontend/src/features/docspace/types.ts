export interface DocSpaceConfig {
  portal_url: string
  enabled: boolean
}

export interface DocSpaceDocument {
  id: number
  title: string
  docspace_file_id: number
  docspace_folder_id: number
  file_ext: string
  content_length: number
  web_url: string
  created_at: string
  updated_at: string
}

export interface DocSpaceUploadResult {
  id: number
  title: string
  docspace_file_id: number
  web_url: string
  file_ext: string
  content_length: number
}
