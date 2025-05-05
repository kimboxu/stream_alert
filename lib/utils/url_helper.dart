class UrlHelper {
  static String normalizeDiscordWebhookUrl(String? url) {
    if (url == null || url.isEmpty) {
      return '';
    }
    
    //discordapp.com을 discord.com으로 변환
    return url.replaceAll(
      'https://discordapp.com/api/webhooks/', 
      'https://discord.com/api/webhooks/',
    );
  }
  
  /// URL이 Discord Webhook URL인지 확인
  static bool isDiscordWebhookUrl(String url) {
    return url.startsWith('https://discord.com/api/webhooks/') || 
           url.startsWith('https://discordapp.com/api/webhooks/');
  }
  
  /// URL에서 불필요한 공백을 제거하고, 앞뒤 공백을 정리
  static String cleanUrl(String url) {
    return url.trim();
  }
}